import unittest

from material_collector.check_scenes import check
from material_collector.html_sheet import parse_scene_table

SCRIPT = "\n".join([
    "魔理沙「将棋を覚えた」",
    "霊夢「へえ」",
    "魔理沙「だが熱が出た」",
    "魔理沙「父は喜んだんだろうな」",
    "魔理沙「そして駒袋をもらった」",
    "霊夢「いいわね」",
    "魔理沙「大切にした」",
])


def warnings(table: str) -> list[list[str]]:
    return [img["warnings"] for img in check(SCRIPT, table)]


class CheckScenesTest(unittest.TestCase):
    def test_trigger_is_parsed_and_not_in_caption(self):
        seg = parse_scene_table("1: 升田=Masuda|升田幸三 @兄弟子/升田\n")[0]
        self.assertEqual(seg["captions"], ["升田幸三"])
        self.assertEqual(seg["triggers"], [["兄弟子", "升田"]])
        self.assertEqual(seg["keywords"][0].en, "Masuda")
        self.assertEqual(parse_scene_table("1: 升田\n")[0]["triggers"], [None])

    def test_good_table_has_no_warnings(self):
        self.assertEqual(warnings("1: 将棋 @将棋\n3: 熱 @熱\n5: 駒袋 @駒袋\n"), [[], [], []])

    def test_switch_too_early(self):
        result = warnings("1: 将棋 @将棋\n3: 駒袋 @駒袋\n")
        self.assertIn("5 行目で初めて", result[1][0])

    def test_switch_too_late(self):
        result = warnings("1: 将棋 @将棋\n3: 熱 @熱/喜ん\n6: 駒袋 @駒袋\n")
        self.assertTrue(any("切り替えが遅すぎる" in w for w in result[2]))
        self.assertTrue(any("霊夢のセリフから始まっている" in w for w in result[2]))

    def test_missing_trigger_and_dash(self):
        result = warnings("1: 将棋\n3: 本人 @-\n5: 駒袋 @手紙\n")
        self.assertIn("きっかけ(@)が書いていない", result[0])
        self.assertEqual(result[1], [])
        self.assertIn("台本のどこにも出てこない", result[2][0])


if __name__ == "__main__":
    unittest.main()
