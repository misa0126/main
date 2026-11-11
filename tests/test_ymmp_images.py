import json
import tempfile
import unittest
from pathlib import Path

from material_collector.ymmp_images import (
    IMAGE_TYPE,
    REMARK,
    VOICE_TYPE,
    add_images,
    main,
    script_utterances,
)

SCRIPT = "魔理沙「一」\n\n霊夢「二」\n魔理沙「三の前半\n三の後半」\n\n魔理沙「四」\n霊夢「五」"
# 空行を除いた行番号: 1=一, 2=二, 3=三(前半), 4=三(後半), 5=四, 6=五
TABLE = "## 導入\n1: 甲子園\n## 本編\n3: 長崎=Nagasaki, 出島=Dejima\n6: 東京\n"


def voice(serif, frame, length):
    return {
        "$type": VOICE_TYPE,
        "CharacterName": "魔理沙",
        "Serif": serif,
        "X": {"Values": [{"Value": 0.0}], "Span": 0.0, "AnimationType": "なし"},
        "Frame": frame,
        "Layer": 2,
        "Length": length,
    }


def project(voices):
    return {
        "Timelines": [
            {
                "VideoInfo": {"FPS": 60, "Width": 1920, "Height": 1080},
                "Items": voices,
                "Length": 0,
                "MaxLayer": 2,
            }
        ]
    }


VOICES = [voice("一", 0, 50), voice("二", 50, 40), voice("三の前半\r\n三の後半", 90, 60), voice("四", 150, 30), voice("五", 180, 20)]


class ScriptTest(unittest.TestCase):
    def test_multiline_serif_is_one_utterance(self):
        utterances, line_map = script_utterances(SCRIPT)
        self.assertEqual(utterances, ["一", "二", "三の前半三の後半", "四", "五"])
        self.assertEqual(line_map, [0, 1, 2, 2, 3, 4])


class AddImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        for name in ["001_甲子園.jpg", "002_長崎.png", "004_東京.jpg", "メモ.txt"]:
            (self.folder / name).write_bytes(b"")

    def tearDown(self):
        self.tmp.cleanup()

    def images(self, proj):
        return [i for i in proj["Timelines"][0]["Items"] if i["$type"] == IMAGE_TYPE]

    def test_places_images_at_scene_starts(self):
        result, placements, notes = add_images(project(VOICES), SCRIPT, TABLE, self.folder)
        spans = [(p.no, p.frame, p.length) for p in placements]
        # 2番目の区切り(セリフ「三」「四」)は画像2枚なので、セリフ1つずつに分ける
        self.assertEqual(spans, [(1, 0, 90), (2, 90, 60), (3, 150, 30), (4, 180, 20)])
        images = self.images(result)
        self.assertEqual([Path(i["FilePath"]).name for i in images], ["001_甲子園.jpg", "002_長崎.png", "004_東京.jpg"])
        self.assertTrue(all(i["Layer"] == 3 and i["Remark"] == REMARK for i in images))
        self.assertEqual(result["Timelines"][0]["MaxLayer"], 3)
        self.assertEqual(result["Timelines"][0]["Length"], 200)
        self.assertIn("Values", images[0]["X"])
        self.assertIsNone(placements[2].path)

    def test_running_twice_replaces_previous_images(self):
        once, _, _ = add_images(project(VOICES), SCRIPT, TABLE, self.folder)
        twice, _, _ = add_images(once, SCRIPT, TABLE, self.folder, layer=3)
        self.assertEqual(len(self.images(twice)), 3)

    def test_aligns_by_text_when_counts_differ(self):
        # 台本に無いセリフがプロジェクトに1つ足されている
        voices = VOICES[:2] + [voice("追加したセリフ", 90, 30)] + [
            voice("三の前半\r\n三の後半", 120, 60),
            voice("四", 180, 30),
            voice("五", 210, 20),
        ]
        _, placements, notes = add_images(project(voices), SCRIPT, TABLE, self.folder)
        self.assertEqual([(p.frame, p.length) for p in placements], [(0, 120), (120, 60), (180, 30), (210, 20)])
        self.assertTrue(any("数が違います" in n for n in notes))

    def test_old_format_timeline(self):
        old = {"Timeline": {"VideoInfo": {}, "Items": [dict(v, X={"From": 0.0}) for v in VOICES], "MaxLayer": 2}}
        result, _, _ = add_images(old, SCRIPT, TABLE, self.folder)
        images = [i for i in result["Timeline"]["Items"] if i["$type"] == IMAGE_TYPE]
        self.assertIn("From", images[0]["X"])

    def test_cli_writes_new_file_and_keeps_original(self):
        source = self.folder / "テスト.ymmp"
        source.write_text(json.dumps(project(VOICES), ensure_ascii=False), encoding="utf-8-sig")
        script = self.folder / "s.txt"
        table = self.folder / "t.txt"
        script.write_text(SCRIPT, encoding="utf-8")
        table.write_text(TABLE, encoding="utf-8")
        main([str(source), str(script), str(table), str(self.folder)])
        output = self.folder / "テスト_画像入り.ymmp"
        data = json.loads(output.read_text(encoding="utf-8-sig"))
        self.assertEqual(len(self.images(data)), 3)
        self.assertEqual(len(self.images(json.loads(source.read_text(encoding="utf-8-sig")))), 0)

    def test_cli_accepts_zip_from_image_list(self):
        import zipfile

        source = self.folder / "テスト.ymmp"
        source.write_text(json.dumps(project(VOICES), ensure_ascii=False), encoding="utf-8-sig")
        (self.folder / "s.txt").write_text(SCRIPT, encoding="utf-8")
        (self.folder / "t.txt").write_text(TABLE, encoding="utf-8")
        archive = self.folder / "download"  # Chromeで名前が付かずに保存された場合
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("001_甲子園.png", b"")
            z.writestr("../002_長崎.png", b"")
        main([str(source), str(self.folder / "s.txt"), str(self.folder / "t.txt"), str(archive)])
        self.assertTrue((self.folder / "download_画像" / "002_長崎.png").exists())
        data = json.loads((self.folder / "テスト_画像入り.ymmp").read_text(encoding="utf-8-sig"))
        self.assertEqual(len(self.images(data)), 2)


    def test_tolerates_names_splits_merges_and_symbols(self):
        # 名前が残っている / 1つのセリフが2つに分かれた / 2つが1つにまとまった / 記号が全角・半角で違う
        voices = [
            voice("魔理沙「一」", 0, 50),
            voice("霊夢「二」", 50, 40),
            voice("三の前半", 90, 30),
            voice("三の後半", 120, 30),
            voice("四！五", 150, 50),
        ]
        _, placements, _ = add_images(project(voices), SCRIPT, TABLE, self.folder)
        # 「五」は「四五」のまとまりの後ろ半分なので、そのセリフの途中(150 + 50 * 1/2)から
        self.assertEqual([(p.frame, p.length) for p in placements], [(0, 90), (90, 60), (150, 25), (175, 25)])

    def test_different_script_is_an_error(self):
        voices = [voice("まったく関係のない話です", 0, 50), voice("ほかの台本のセリフ", 50, 50)]
        with self.assertRaises(ValueError) as caught:
            add_images(project(voices), SCRIPT, TABLE, self.folder)
        self.assertIn("まったく関係のない話です", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
