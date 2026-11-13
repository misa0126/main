import json
import re
import unittest
from pathlib import Path

from material_collector.thumbnail import build_thumbnail_page, parse_thumb_table

TABLE = """# メモ
名前: 大山康晴
写真: 大山康晴 晩年=Yasuharu Oyama
写真: 大山康晴 若い頃

## 案1
型: 右に写真
文字: 69歳まで|{A級}
霊夢: 驚き

## 案2
型: 比較
文字: 少年が|{王}に
写真: 2, 1
ラベル: 若い頃, 晩年
"""


class ThumbTableTest(unittest.TestCase):
    def test_parse(self):
        data = parse_thumb_table(TABLE)
        self.assertEqual(data["name"], "大山康晴")
        self.assertEqual(data["photos"][1], {"ja": "大山康晴 若い頃", "en": "大山康晴 若い頃"})
        first, second = data["plans"]
        self.assertEqual((first["reimu"], first["marisa"], first["photos"]), ("驚き", "ふつう", [1]))
        self.assertEqual((second["photos"], second["labels"]), ([2, 1], ["若い頃", "晩年"]))

    def test_face_up_is_mono_and_face_can_be_hidden(self):
        table = TABLE.replace("型: 右に写真", "型: 顔アップ").replace("霊夢: 驚き", "霊夢: なし")
        first = parse_thumb_table(table)["plans"][0]
        self.assertEqual((first["layout"], first["mono"], first["reimu"]), ("顔アップ", True, "なし"))
        self.assertFalse(parse_thumb_table(table.replace("霊夢: なし", "霊夢: なし\n白黒: いいえ"))["plans"][0]["mono"])

    def test_speech_bubbles(self):
        table = TABLE.replace("型: 右に写真", "型: 吹き出し\n上の文字: 上\n霊夢のセリフ: えっ|ほんと？\n魔理沙のセリフ: そうだぜ")
        first = parse_thumb_table(table)["plans"][0]
        self.assertEqual((first["layout"], first["top"], first["reimu_says"], first["marisa_says"]), ("吹き出し", "上", "えっ|ほんと？", "そうだぜ"))

    def test_errors(self):
        for bad in [TABLE.replace("霊夢: 驚き", "霊夢: 爆笑"), TABLE.replace("写真: 2, 1", "写真: 2"),
                    TABLE.replace("写真: 2, 1", "写真: 3, 1"), TABLE.replace("型: 右に写真", "型: 縦長"),
                    TABLE.replace("名前: 大山康晴\n", "")]:
            with self.assertRaises(ValueError):
                parse_thumb_table(bad)

    def test_build_embeds_faces(self):
        html = build_thumbnail_page(TABLE)
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(len(data["faces"]), 14)
        self.assertTrue(data["faces"]["reimu_驚き"].startswith("data:image/webp;base64,"))
        self.assertIn("<title>大山康晴 サムネ作成</title>", html)

    def test_example_table_builds(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "oyama_yasuharu_thumb.txt"
        self.assertEqual(len(parse_thumb_table(path.read_text(encoding="utf-8"))["plans"]), 3)


if __name__ == "__main__":
    unittest.main()
