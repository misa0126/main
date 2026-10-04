import json
import tempfile
import unittest
from pathlib import Path

from material_collector.pipeline import PipelineConfig, run_pipeline
from material_collector.relevance import Verdict
from material_collector.sources import Candidate, Keyword
from tests.fakes import FakeResponse, FakeSession, make_jpeg


class FakeExtractor:
    def extract(self, scene_text):
        return [Keyword("銀巴里", "Gin Pari"), Keyword("三島由紀夫", "Yukio Mishima")]


class FakeSource:
    def __init__(self, name, candidates):
        self.name = name
        self._candidates = candidates

    def search(self, keyword, limit):
        return [c for c in self._candidates if c.title.startswith(keyword.ja)][:limit]


class FakeChecker:
    def check(self, image_path, scene_text, keyword, candidate):
        if "別人" in candidate.title:
            return Verdict(ok=False, reason="別人")
        return Verdict(ok=True, reason="合っている")


class FakeGoogle:
    def __init__(self):
        self.calls = 0

    def fetch(self, keyword, dest_dir, max_num):
        self.calls += 1
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "000001.jpg"
        path.write_bytes(make_jpeg(seed=50 + self.calls))
        return [(path, Candidate(source="google", image_url=f"https://g/{self.calls}.jpg", title=keyword.ja, verified=False))]


def cand(title, n, license_name="CC BY 4.0"):
    return Candidate(
        source="wikimedia",
        image_url=f"https://img/{n}.jpg",
        title=title,
        page_url=f"https://page/{n}",
        author=f"作者{n}",
        license=license_name,
    )


def image_routes(sizes):
    def respond(url, params):
        n = int(url.rsplit("/", 1)[1].split(".")[0])
        w, h = sizes.get(n, (800, 600))
        return FakeResponse(content=make_jpeg(w, h, seed=n), content_type="image/jpeg")

    return {"https://img/": respond}


class PipelineTest(unittest.TestCase):
    def run_with(self, script, sources, google, images_per_scene=3, sizes=None):
        tmp = Path(tempfile.mkdtemp())
        script_path = tmp / "script.txt"
        script_path.write_text(script, encoding="utf-8")
        config = PipelineConfig(
            script_path=script_path,
            output_dir=tmp / "out",
            images_per_scene=images_per_scene,
            google_fallback=google is not None,
        )
        manifest = run_pipeline(
            config,
            extractor=FakeExtractor(),
            sources=sources,
            google=google,
            checker=FakeChecker(),
            session=FakeSession(image_routes(sizes or {})),
            log=lambda *_: None,
        )
        return tmp / "out", manifest

    def test_licensed_sources_fill_scene_without_google(self):
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1), cand("銀巴里 別人", 2), cand("三島由紀夫 1", 3), cand("三島由紀夫 2", 4)])
        google = FakeGoogle()
        out, manifest = self.run_with("魔理沙「銀巴里だぜ」", [source], google)

        scene = manifest["scenes"][0]
        self.assertEqual([i["title"] for i in scene["selected_images"]], ["銀巴里 1", "三島由紀夫 1", "三島由紀夫 2"])
        self.assertEqual(scene["needs_review_images"], [])
        self.assertEqual(scene["rejected_by_relevance_check"][0]["reason"], "別人")
        self.assertEqual(google.calls, 0)
        self.assertTrue((out / "scene_001" / "selected" / "003.jpg").exists())
        credits = (out / "CREDITS.txt").read_text(encoding="utf-8")
        self.assertIn("作者1", credits)
        self.assertIn("https://page/3", credits)
        viewer = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="scene_001/selected/001.jpg"', viewer)
        self.assertIn('<span class="speaker marisa">魔理沙</span>', viewer)
        self.assertIn("内容が合わず除外した候補: 1枚", viewer)
        saved = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["scenes"][0]["selected_images"][0]["license_verified"])

    def test_google_fills_shortage_into_needs_review(self):
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1), cand("三島由紀夫 小さい", 2)])
        google = FakeGoogle()
        out, manifest = self.run_with("魔理沙「銀巴里だぜ」", [source], google, sizes={2: (200, 150)})

        scene = manifest["scenes"][0]
        self.assertEqual(len(scene["selected_images"]), 1)
        self.assertEqual(len(scene["needs_review_images"]), 2)
        self.assertFalse(scene["needs_review_images"][0]["license_verified"])
        self.assertTrue((out / "scene_001" / "needs_review" / "001.jpg").exists())
        self.assertIn('class="card review"', (out / "index.html").read_text(encoding="utf-8"))
        # 要確認の画像はクレジット一覧に入れない
        self.assertNotIn("https://g/", (out / "CREDITS.txt").read_text(encoding="utf-8"))

    def test_duplicate_images_are_skipped(self):
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1), cand("銀巴里 同じ画像", 1)])
        _, manifest = self.run_with("霊夢「同じ」", [source], None, images_per_scene=2)
        self.assertEqual(len(manifest["scenes"][0]["selected_images"]), 1)

    def test_multiple_scenes(self):
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1), cand("銀巴里 2", 2), cand("三島由紀夫 1", 3)])
        out, manifest = self.run_with("魔理沙「A」\n\n霊夢「B」", [source], None, images_per_scene=1)
        self.assertEqual(len(manifest["scenes"]), 2)
        self.assertTrue((out / "scene_002" / "keywords.txt").exists())


class FailingOnceExtractor(FakeExtractor):
    def extract(self, scene_text):
        if "壊れる" in scene_text:
            raise RuntimeError("API timeout")
        return super().extract(scene_text)


class SceneErrorTest(PipelineTest):
    def test_one_failing_scene_does_not_stop_the_run(self):
        tmp = Path(tempfile.mkdtemp())
        script_path = tmp / "script.txt"
        script_path.write_text("魔理沙「壊れる」\n\n霊夢「大丈夫」", encoding="utf-8")
        source = FakeSource("wikimedia", [cand("銀巴里 1", 1)])
        config = PipelineConfig(script_path=script_path, output_dir=tmp / "out", images_per_scene=1, google_fallback=False)
        manifest = run_pipeline(
            config,
            extractor=FailingOnceExtractor(),
            sources=[source],
            checker=FakeChecker(),
            session=FakeSession(image_routes({})),
            log=lambda *_: None,
        )
        first, second = manifest["scenes"]
        self.assertIn("API timeout", first["error"])
        self.assertEqual(len(second["selected_images"]), 1)
        self.assertIn("エラーで処理できませんでした", (tmp / "out" / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
