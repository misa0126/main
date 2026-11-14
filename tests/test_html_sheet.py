import json
import re
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
        self.assertIn('id="ymm4"', html)

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
