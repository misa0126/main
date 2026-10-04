import unittest

from material_collector.keyword_extractor import _parse_keywords
from material_collector.relevance import _parse_verdict
from material_collector.sources import Keyword, is_reusable_license
from material_collector.sources.met import MetMuseumSource
from material_collector.sources.openverse import OpenverseSource
from material_collector.sources.stock import PexelsSource, PixabaySource
from material_collector.sources.wikimedia import WikimediaCommonsSource
from tests.fakes import FakeResponse, FakeSession

KW = Keyword(ja="三島由紀夫", en="Yukio Mishima")


class LicenseTest(unittest.TestCase):
    def test_reusable(self):
        for name in ["CC BY-SA 4.0", "CC BY 2.0", "Public domain", "CC0", "PD-old-70", "Public Domain Mark"]:
            self.assertTrue(is_reusable_license(name), name)

    def test_not_reusable(self):
        for name in ["CC BY-NC 2.0", "CC BY-ND 4.0", "CC BY-NC-SA 3.0", "GFDL", "Fair use", "", "All rights reserved"]:
            self.assertFalse(is_reusable_license(name), name)


def _wm_page(index, title, license_name, mime="image/jpeg"):
    return {
        "index": index,
        "title": f"File:{title}.jpg",
        "imageinfo": [
            {
                "url": f"https://upload.wikimedia.org/{title}.jpg",
                "thumburl": f"https://upload.wikimedia.org/thumb/{title}.jpg",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title}.jpg",
                "mime": mime,
                "extmetadata": {
                    "LicenseShortName": {"value": license_name},
                    "LicenseUrl": {"value": "https://example.org/license"},
                    "Artist": {"value": '<a href="/wiki/User:X">写真家 &amp; 助手</a>'},
                    "ObjectName": {"value": title},
                },
            }
        ],
    }


class WikimediaTest(unittest.TestCase):
    def test_filters_license_and_mime_and_keeps_order(self):
        pages = {
            "3": _wm_page(2, "B", "CC BY-SA 4.0"),
            "1": _wm_page(1, "A", "Public domain"),
            "5": _wm_page(3, "C", "CC BY-NC 2.0"),
            "7": _wm_page(4, "D", "CC0", mime="image/svg+xml"),
        }
        session = FakeSession({"https://commons.wikimedia.org": FakeResponse(json_data={"query": {"pages": pages}})})
        results = WikimediaCommonsSource(session).search(KW, 5)
        self.assertEqual([c.title for c in results], ["A", "B"])
        self.assertEqual(results[0].author, "写真家 & 助手")
        self.assertEqual(results[0].image_url, "https://upload.wikimedia.org/thumb/A.jpg")
        self.assertTrue(results[0].verified)
        # 日本語で足りなければ英語でも検索する
        queries = [params["gsrsearch"] for _, params in session.calls]
        self.assertEqual(queries, ["三島由紀夫 filetype:bitmap", "Yukio Mishima filetype:bitmap"])

    def test_network_error_returns_empty(self):
        session = FakeSession({"https://commons.wikimedia.org": FakeResponse(status_code=503)})
        self.assertEqual(WikimediaCommonsSource(session).search(KW, 3), [])


class OpenverseTest(unittest.TestCase):
    def test_parses_results(self):
        data = {
            "results": [
                {
                    "url": "https://live.staticflickr.com/1.jpg",
                    "title": "Ginza",
                    "creator": "someone",
                    "license": "by-sa",
                    "license_version": "2.0",
                    "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
                    "foreign_landing_url": "https://flickr.com/photos/1",
                    "source": "flickr",
                },
                {"url": "https://x/2.jpg", "license": "by-nc", "license_version": "2.0", "source": "flickr"},
            ]
        }
        session = FakeSession({"https://api.openverse.org": FakeResponse(json_data=data)})
        results = OpenverseSource(session).search(KW, 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].license, "CC BY-SA 2.0")
        self.assertEqual(results[0].source, "openverse:flickr")
        self.assertEqual(session.calls[0][1]["q"], "Yukio Mishima")
        self.assertEqual(session.calls[0][1]["license_type"], "commercial,modification")


class MetTest(unittest.TestCase):
    def test_only_public_domain(self):
        def objects(url, params):
            object_id = url.rsplit("/", 1)[1]
            return FakeResponse(
                json_data={
                    "isPublicDomain": object_id != "2",
                    "primaryImage": f"https://images.metmuseum.org/{object_id}.jpg",
                    "title": f"Object {object_id}",
                    "objectURL": f"https://www.metmuseum.org/art/collection/search/{object_id}",
                }
            )

        session = FakeSession(
            {
                "https://collectionapi.metmuseum.org/public/collection/v1/search": FakeResponse(
                    json_data={"objectIDs": [1, 2, 3]}
                ),
                "https://collectionapi.metmuseum.org/public/collection/v1/objects/": objects,
            }
        )
        results = MetMuseumSource(session).search(KW, 5)
        self.assertEqual([c.title for c in results], ["Object 1", "Object 3"])

    def test_no_hits(self):
        session = FakeSession({"https://collectionapi": FakeResponse(json_data={"total": 0, "objectIDs": None})})
        self.assertEqual(MetMuseumSource(session).search(KW, 5), [])


class StockTest(unittest.TestCase):
    def test_pexels(self):
        data = {"photos": [{"src": {"large2x": "https://images.pexels.com/1.jpg"}, "url": "https://pexels.com/p/1", "photographer": "P"}]}
        session = FakeSession({"https://api.pexels.com": FakeResponse(json_data=data)})
        results = PexelsSource("key", session).search(KW, 3)
        self.assertEqual(results[0].license, "Pexels License")
        self.assertEqual(results[0].author, "P")

    def test_pixabay_uses_japanese_and_min_per_page(self):
        data = {"hits": [{"largeImageURL": "https://pixabay.com/1.jpg", "pageURL": "https://pixabay.com/p/1", "user": "U", "tags": "a, b"}]}
        session = FakeSession({"https://pixabay.com/api/": FakeResponse(json_data=data)})
        results = PixabaySource("key", session).search(KW, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(session.calls[0][1]["q"], "三島由紀夫")
        self.assertEqual(session.calls[0][1]["per_page"], 3)


class ParseTest(unittest.TestCase):
    def test_keywords_json_objects(self):
        raw = '```json\n[{"ja": "銀巴里", "en": "Gin Pari chanson cafe"}, {"ja": "長崎"}]\n```'
        self.assertEqual(
            _parse_keywords(raw, 3),
            [Keyword("銀巴里", "Gin Pari chanson cafe"), Keyword("長崎", "長崎")],
        )

    def test_keywords_plain_strings(self):
        self.assertEqual(_parse_keywords('["A", "B", "C"]', 2), [Keyword("A", "A"), Keyword("B", "B")])

    def test_verdict(self):
        v = _parse_verdict('{"ok": false, "reason": "別人の写真"}')
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "別人の写真")
        self.assertTrue(v.checked)
        broken = _parse_verdict("わかりません")
        self.assertTrue(broken.ok)
        self.assertFalse(broken.checked)


if __name__ == "__main__":
    unittest.main()
