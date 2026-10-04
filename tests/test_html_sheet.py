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
        self.assertEqual(second["keywords"], [{"ja": "長崎", "en": "Nagasaki"}])
        self.assertIn("<title>テスト 素材シート</title>", html)

    def test_start_beyond_script_is_an_error(self):
        with self.assertRaises(ValueError):
            build_sheet(SCRIPT, "## a\n1: x\n9: y\n", "テスト")

    def test_nishizaki_table_matches_script(self):
        build_sheet(
            Path("scripts/nishizaki_yoshinobu.txt").read_text(encoding="utf-8"),
            Path("scripts/nishizaki_yoshinobu_scenes.txt").read_text(encoding="utf-8"),
            "西崎義展",
        )


if __name__ == "__main__":
    unittest.main()
