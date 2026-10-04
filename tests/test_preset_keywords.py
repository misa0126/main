import tempfile
import unittest
from pathlib import Path

from material_collector.pipeline import PipelineConfig, run_pipeline
from material_collector.preset_keywords import PresetKeywordExtractor, parse_keyword_table
from material_collector.sources import Keyword
from tests.fakes import FakeSession
from tests.test_pipeline import FakeSource, cand, image_routes

TABLE = """# メモ
1: 銀巴里=Gin Pari, 三島由紀夫
2: -
3：長崎、出島=Dejima
"""


class ParseTableTest(unittest.TestCase):
    def test_parse(self):
        table = parse_keyword_table(TABLE)
        self.assertEqual(table[1], [Keyword("銀巴里", "Gin Pari"), Keyword("三島由紀夫", "三島由紀夫")])
        self.assertEqual(table[2], [])
        self.assertEqual(table[3], [Keyword("長崎", "長崎"), Keyword("出島", "Dejima")])

    def test_bad_line(self):
        with self.assertRaises(ValueError):
            parse_keyword_table("銀巴里, 三島")

    def test_miwa_table_covers_every_scene(self):
        script = Path("scripts/miwa_akihiro.txt").read_text(encoding="utf-8")
        table = Path("scripts/miwa_akihiro_keywords.txt").read_text(encoding="utf-8")
        self.assertEqual(PresetKeywordExtractor(script, table).missing, [])


class PresetPipelineTest(unittest.TestCase):
    def test_runs_without_claude(self):
        tmp = Path(tempfile.mkdtemp())
        script_path = tmp / "script.txt"
        script_path.write_text("魔理沙「銀巴里だぜ」\n\n霊夢「へえ」\n\n魔理沙「長崎だぜ」\n\n魔理沙「表にない」", encoding="utf-8")
        table_path = tmp / "keywords.txt"
        table_path.write_text(TABLE, encoding="utf-8")
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1), cand("長崎 1", 2)])
        config = PipelineConfig(
            script_path=script_path,
            output_dir=tmp / "out",
            images_per_scene=1,
            google_fallback=False,
            check_relevance=False,
            keyword_table_path=table_path,
        )
        manifest = run_pipeline(config, sources=[source], session=FakeSession(image_routes({})), log=lambda *_: None)
        scenes = manifest["scenes"]
        self.assertEqual(scenes[0]["selected_images"][0]["title"], "銀巴里 1")
        self.assertIsNone(scenes[0]["selected_images"][0]["relevance"])
        self.assertTrue(scenes[1]["skipped"])
        self.assertEqual(scenes[2]["selected_images"][0]["title"], "長崎 1")
        self.assertIn("キーワード表にありません", scenes[3]["error"])
        viewer = (tmp / "out" / "index.html").read_text(encoding="utf-8")
        self.assertIn("前のシーンの画像のまま", viewer)
        self.assertIn("内容チェックなし", viewer)
        self.assertIn("画像なし 1シーン", viewer)  # キーワード表にないシーン4だけ


if __name__ == "__main__":
    unittest.main()
