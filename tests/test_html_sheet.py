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
        self.assertEqual(first["images"], [{"no": 1, "ja": "甲子園", "en": "甲子園", "native": ""}])
        self.assertEqual(second["images"], [{"no": 2, "ja": "長崎", "en": "Nagasaki", "native": ""}])
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
