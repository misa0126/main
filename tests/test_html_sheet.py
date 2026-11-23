import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from material_collector.html_sheet import build_sheet, parse_scene_table

SCRIPT = "魔理沙「一」\n\n霊夢「二」\n魔理沙「三」\n\n魔理沙「四」"


class SceneTableTest(unittest.TestCase):
    def test_parse_topics_and_keywords(self):
        segments = parse_scene_table("# メモ\n## 導入\n1: 甲子園=Koshien\n## 本編\n3: 長崎, 出島=Dejima\n")
        self.assertEqual([s["topic"] for s in segments], ["導入", "本編"])
        self.assertEqual(segments[1]["start"], 3)
        self.assertEqual(segments[1]["keywords"][1].en, "Dejima")

    def test_rejects_unordered_starts(self):
        with self.assertRaises(ValueError):
            parse_scene_table("## a\n3: x\n1: y\n")

    def test_build_splits_lines_by_start(self):
        html = build_sheet(SCRIPT, "## 導入\n1: 甲子園\n3: 長崎=Nagasaki\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        first, second = data["segments"]
        self.assertEqual((first["start"], first["end"]), (1, 2))
        self.assertEqual([line["text"] for line in second["lines"]], ["三", "四"])
        self.assertEqual(first["images"], [{"no": 1, "ja": "甲子園", "en": "甲子園", "native": "", "caption": ""}])
        self.assertEqual(second["images"], [{"no": 2, "ja": "長崎", "en": "Nagasaki", "native": "", "caption": ""}])
        self.assertIn("<title>テスト 画像リスト</title>", html)

    def test_data_for_ymm4_placement(self):
        script = "魔理沙「一」\n霊夢「二の前半、\n二の後半」\n魔理沙「三」"
        html = build_sheet(script, "## a\n1: x\n3: y\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(data["utterances"], ["一", "二の前半二の後半", "三"])
        self.assertEqual([s["u"] for s in data["segments"]], [0, 1])
        self.assertEqual(data["lineU"], [0, 1, 1, 2])  # 画面で区切りを動かすときの、行ごとのセリフ番号
        self.assertIn('id="edit"', html)
        self.assertIn('id="ymm4"', html)

    def test_preloaded_images_by_number(self):
        # Claude が選んだ画像(001_ワード.jpg)を番号どおりに最初から入れておく。番号のない画像・範囲外は使わない
        tmp = Path(self.id().replace(".", "_") + "_imgs")
        tmp.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "001_甲子園.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "002_長崎.png").write_bytes(b"\x89PNGx")
        (tmp / "009_範囲外.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "メモ.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "一覧.txt").write_text("x", encoding="utf-8")
        from material_collector.html_sheet import load_images
        html = build_sheet(SCRIPT, "## 導入\n1: 甲子園\n3: 長崎\n", "テスト", preload=load_images(tmp))
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(sorted(data["preload"]), ["1", "2"])
        self.assertTrue(data["preload"]["1"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(data["preload"]["2"].startswith("data:image/png;base64,"))

    def test_side_by_side_images(self):
        # 「A + B」は同時に横に並べる。「+3: C」は前の区切りの画像を出したまま、3行目から横に足す
        table = "## a\n1: 甲 @x + 乙 @y\n+3: 丙 @z\n"
        seg = parse_scene_table(table)[0]
        self.assertEqual([k.ja for k in seg["keywords"]], ["甲", "乙", "丙"])
        self.assertEqual(seg["joins"], [False, True, True])
        self.assertEqual(seg["ats"], [None, None, 3])
        html = build_sheet(SCRIPT, table, "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        images = data["segments"][0]["images"]
        self.assertNotIn("with", images[0])
        self.assertTrue(images[1]["with"])
        self.assertEqual((images[2]["with"], images[2]["at"]), (True, 3))
        with self.assertRaises(ValueError):
            parse_scene_table("## a\n1: 甲\n3: 乙\n+2: 丙\n")  # 区切りより前の行には足せない

    def test_readings_are_keyed_by_utterance(self):
        script = "魔理沙「一」\n霊夢「二の前半、\n二の後半」\n魔理沙「三」"
        html = build_sheet(script, "## a\n1: x\n", "テスト", "# メモ\n2: にのぜんはん、にのこうはん\n4: さん\n")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(data["readings"], {"1": "にのぜんはん、にのこうはん", "2": "さん"})
        self.assertNotIn("readings", json.loads(re.search(r"const DATA = (\{.*?\});\n", build_sheet(script, "## a\n1: x\n", "テスト")).group(1)))

    def test_reading_on_continuation_line_is_an_error(self):
        script = "魔理沙「一」\n霊夢「二の前半、\n二の後半」"
        with self.assertRaises(ValueError):
            build_sheet(script, "## a\n1: x\n", "テスト", "3: にのこうはん\n")

    def test_caption_after_bar(self):
        html = build_sheet(SCRIPT, "## a\n1: 升田幸三 若い頃=young Kozo Masuda|升田幸三, 高野山=Mount Koya\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        first, second = data["segments"][0]["images"]
        self.assertEqual((first["ja"], first["en"], first["caption"]), ("升田幸三 若い頃", "young Kozo Masuda", "升田幸三"))
        self.assertEqual(second["caption"], "")

    def test_native_language_and_numbering_across_segments(self):
        html = build_sheet(SCRIPT, "## a\n1: ピアフ=Edith Piaf=Édith Piaf, パリ=Paris\n3: 長崎\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        first, second = data["segments"]
        self.assertEqual(first["images"][0]["native"], "Édith Piaf")
        self.assertEqual([i["no"] for i in first["images"] + second["images"]], [1, 2, 3])

    def test_segment_without_images_is_an_error(self):
        with self.assertRaises(ValueError):
            build_sheet(SCRIPT, "## a\n1: x\n3: -\n", "テスト")

    def test_start_beyond_script_is_an_error(self):
        with self.assertRaises(ValueError):
            build_sheet(SCRIPT, "## a\n1: x\n9: y\n", "テスト")

    def test_nishizaki_table_matches_script(self):
        build_sheet(
            Path("scripts/nishizaki_yoshinobu.txt").read_text(encoding="utf-8"),
            Path("scripts/nishizaki_yoshinobu_scenes.txt").read_text(encoding="utf-8"),
            "西崎義展",
        )

    def test_oyama_table_matches_script(self):
        build_sheet(
            Path("scripts/oyama_yasuharu.txt").read_text(encoding="utf-8"),
            Path("scripts/oyama_yasuharu_scenes.txt").read_text(encoding="utf-8"),
            "大山康晴",
        )

    def test_has_yahoo_and_bing_buttons(self):
        html = build_sheet(SCRIPT, "## a\n1: x\n", "テスト")
        self.assertIn("https://search.yahoo.co.jp/image/search?p=", html)
        self.assertIn("https://www.bing.com/images/search?q=", html)


if __name__ == "__main__":
    unittest.main()


class AquesTalkKanaTest(unittest.TestCase):
    def test_du_and_di_become_zu_and_ji(self):
        from material_collector.html_sheet import parse_yomi_table
        self.assertEqual(parse_yomi_table("1: ねばりづよい、ちぢむ。"), {1: "ねばりずよい、ちじむ。"})


class PatchHatsuonTest(unittest.TestCase):
    """YMM4の読みは「/」(抑揚)や数字のタグを残し、ちがうかなだけを直す(HTMLの中のJavaScriptを node で動かす)"""

    def run_patch(self, hatsuon, reading):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node がない")
        template = (Path(__file__).resolve().parents[1] / "material_collector" / "html_sheet_template.html").read_text(encoding="utf-8")
        start = template.index("function hiraOf")
        end = template.index("\n}\n", template.index("function patchHatsuon")) + 3
        code = template[start:end] + "\nconst a = JSON.parse(process.argv[1]); process.stdout.write(patchHatsuon(a[0], a[1]));"
        return subprocess.run(["node", "-e", code, json.dumps([hatsuon, reading])], capture_output=True, text=True, encoding="utf-8", check=True).stdout

    def test_keeps_accent_marks_and_fixes_only_the_misread_word(self):
        self.assertEqual(
            self.run_patch("おおい/なか/しょうぎで、こま/どうしの/れんけいを/ねばりずよい", "おおいちゅうしょうぎで、こまどうしの、れんけいおねばりづよい。"),
            "おおい/ちゅう/しょうぎで、こま/どうしの/れんけいを/ねばりずよい",
        )

    def test_number_tags_become_the_table_kana(self):
        hatsuon = "<NUMK VAL=1952 COUNTER=ねん>からの<NUMK VAL=3 COUNTER=ねんかん>わ、めいじんと/おうしょうの_フたつの/たいとるを/も_チつずけた"
        self.assertEqual(
            self.run_patch(hatsuon, "せんきゅうひゃくごじゅうにねんからのさんねんかんわ、めいじんとおうしょうの、ふたつのたいとるおもちつづけた。"),
            "せんきゅうひゃくごじゅうにねんからのさんねんかんわ、めいじんと/おうしょうの_フたつの/たいとるを/も_チつずけた",
        )
        self.assertEqual(self.run_patch("しがつ<NUMK VAL=1 COUNTER=にち>に/しゅっぱつ", "しがつついたちにしゅっぱつ"), "しがつついたちに/しゅっぱつ")

    def test_name_reading(self):
        self.assertEqual(self.run_patch("ますだ/こうぞう、かどた/みつおと", "ますだこうぞう、かくたみつおと"), "ますだ/こうぞう、かくた/みつおと")
        # アクセント(')も残す
        self.assertEqual(self.run_patch("かどた'さんわ/き'た", "かくたさんわきた"), "かくた'さんわ/き'た")

    def test_english_words(self):
        # YMM4がかなにした英語の読みがちがうとき
        self.assertEqual(self.run_patch("あぷれ/の/しんさく", "あっぷるのしんさく"), "あっぷる/の/しんさく")
        # 英字のまま残っていたとき
        self.assertEqual(self.run_patch("iPhone/を/かった", "あいふぉんおかった"), "あいふぉん/を/かった")

    def test_uppercase_titles_read_as_words(self):
        # 大文字の曲名・本のタイトルを、YMM4が1文字ずつ読んでいたとき
        self.assertEqual(self.run_patch("えいちいーえるぴー/を/きいた", "へるぷおきいた"), "へるぷ/を/きいた")
        self.assertEqual(self.run_patch("ざ/ふぁーすと/えすえるえーえむ/だんく/が", "ざふぁーすとすらむだんくが"), "ざ/ふぁーすと/すらむ/だんく/が")
        self.assertEqual(self.run_patch("HELP/を/きいた", "へるぷおきいた"), "へるぷ/を/きいた")

    def test_uppercase_titles(self):
        # 大文字のタイトルを1文字ずつ読んでいたとき
        self.assertEqual(self.run_patch("える/おー/ぶい/いー/の/うた", "らぶのうた"), "らぶ/の/うた")
        # 大文字のまま残っていたとき(全角も)
        self.assertEqual(self.run_patch("HELLO/を/ききながら", "はろーおききながら"), "はろー/を/ききながら")
        self.assertEqual(self.run_patch("ＴＲＵＥ/の/かし", "とぅるーのかし"), "とぅるー/の/かし")

    def test_numbers_are_not_read_twice_and_commas_stay(self):
        hatsuon = "<NUMK VAL=1944 COUNTER=ねん><NUMK VAL=4 COUNTER=がつ>、<NUMK VAL=21 COUNTER=さい>の/おおやまの/もとに"
        self.assertEqual(
            self.run_patch(hatsuon, "せんきゅうひゃくよんじゅうよねんしがつ、にじゅういっさいのおおやまのもとに"),
            "せんきゅうひゃくよんじゅうよねんしがつ、にじゅういっさいの/おおやまの/もとに",
        )
        # 数字の読みが、前後の言葉と偶然ずれて合わさっても、タグを残して二重に読まない
        out = self.run_patch("<NUMK VAL=2 COUNTER=かい>めの/かいぎで、<NUMK VAL=1 COUNTER=にち>に/きまった", "にかいめのかいぎで、ついたちにきまった")
        self.assertNotIn("<", out)
        self.assertEqual(re.sub(r"[/、]", "", out), "にかいめのかいぎでついたちにきまった")
        self.assertIn("かいぎで、", out)


class ResizeVoicesTest(unittest.TestCase):
    """読みを直して拍の数が変わったセリフは、声の長さを読みに合わせて変え、後ろの物をずらす(ユーザーの指摘:
    長さがそのままだと間が空いたり、声が途中で切れたりした)"""

    def run_resize(self, items, fixed_index, before, after):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node がない")
        template = (Path(__file__).resolve().parents[1] / "material_collector" / "html_sheet_template.html").read_text(encoding="utf-8")
        start = template.index("function moraOf")
        end = template.index("\n}\n", template.index("function resizeVoices")) + 3
        code = template[start:end] + (
            "\nconst a = JSON.parse(process.argv[1]); const items = a[0];"
            "const voices = items.filter(i => i.$type === 'V');"
            "const fixed = a[1].map(([k, b, f]) => ({ voice: voices[k], before: b, after: f }));"
            "voices.forEach((v, k) => { const f = fixed.find(x => x.voice === v); if (f) v.Hatsuon = f.after; });"
            "const n = resizeVoices(items, voices, fixed);"
            "process.stdout.write(JSON.stringify({ n, items }));"
        )
        out = subprocess.run(["node", "-e", code, json.dumps([items, [[fixed_index, before, after]]])],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        return json.loads(out)

    def items(self):
        return [
            {"$type": "V", "CharacterName": "魔理沙", "Hatsuon": "あいうえおかきくけこ", "Frame": 0, "Length": 100},
            {"$type": "T", "Frame": 0, "Length": 100},          # そのセリフの立ち絵
            {"$type": "V", "CharacterName": "霊夢", "Hatsuon": "さしすせそ", "Frame": 110, "Length": 50},
            {"$type": "BGM", "Frame": 0, "Length": 300},        # 全体に流れる物
        ]

    def test_longer_reading_pushes_later_items(self):
        r = self.run_resize(self.items(), 0, "あいうえおかきくけこ", "あいうえおかきくけこさしすせそ")
        v1, stand, v2, bgm = r["items"]
        self.assertEqual(r["n"], 1)
        self.assertEqual((v1["Frame"], v1["Length"]), (0, 150))
        self.assertEqual((stand["Frame"], stand["Length"]), (0, 150))
        self.assertEqual((v2["Frame"], v2["Length"]), (160, 50))   # 間(10フレーム)はそのまま
        self.assertEqual((bgm["Frame"], bgm["Length"]), (0, 350))

    def test_shorter_reading_pulls_later_items(self):
        r = self.run_resize(self.items(), 0, "あいうえおかきくけこ", "あいうえお")
        v1, _, v2, _ = r["items"]
        self.assertEqual(v1["Length"], 50)
        self.assertEqual(v2["Frame"], 60)

    def test_same_mora_count_keeps_length(self):
        r = self.run_resize(self.items(), 0, "あいうえおかきくけこ", "あいうえおかきくけそ")
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["items"][2]["Frame"], 110)

    def test_small_kana_do_not_count(self):
        # 「きゃ」は1拍。「ぎゃー」は2拍
        r = self.run_resize(self.items(), 0, "あいうえおかきくけこ", "きゃきゅきょしゃしゅしょちゃちゅちょにゃ")
        self.assertEqual(r["n"], 0)

    def test_number_tag_uses_speaker_rate(self):
        items = self.items()
        items.append({"$type": "V", "CharacterName": "魔理沙", "Hatsuon": "たちつてとなにぬねの", "Frame": 200, "Length": 100})
        items[0]["Hatsuon"] = "<NUMK VAL=1923 COUNTER=ねん>"
        r = self.run_resize(items, 0, "<NUMK VAL=1923 COUNTER=ねん>", "せんきゅうひゃくにじゅうさんねん")
        # 魔理沙のほかのセリフは1拍10フレーム。「せんきゅうひゃくにじゅうさんねん」は13拍
        self.assertEqual(r["items"][0]["Length"], 130)
