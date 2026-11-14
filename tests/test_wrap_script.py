import unittest

from material_collector.wrap_script import renumber, wrap_body, wrap_script


class WrapBodyTest(unittest.TestCase):
    def test_short_line_is_kept(self):
        self.assertEqual(wrap_body("それじゃあ、今回はエイミー・ワインハウスの生涯を詳しく見ていくぜ！"), ["それじゃあ、今回はエイミー・ワインハウスの生涯を詳しく見ていくぜ！"])

    def test_user_examples(self):
        # ユーザーが示した改行の位置
        cases = {
            "しかも世界中で大ヒットした代表曲は、『リハビリ施設には行かない』と言い張る歌なんだぜ":
                ["しかも世界中で大ヒットした代表曲は、", "『リハビリ施設には行かない』と言い張る歌なんだぜ"],
            "お父さんのミッチはタクシーの運転手、お母さんのジャニスは薬剤師で、4つ上にお兄さんのアレックスがいた":
                ["お父さんのミッチはタクシーの運転手、お母さんのジャニスは薬剤師で、", "4つ上にお兄さんのアレックスがいた"],
            "お母さんの親戚にも、楽団でトランペットなどの管楽器を吹く人や、ドラムを叩く人がいた":
                ["お母さんの親戚にも、楽団でトランペットなどの管楽器を吹く人や、", "ドラムを叩く人がいた"],
            "そして、エイミーの音楽に一番大きな影響を与えたのが、お父さん方のおばあちゃんのシンシアだ":
                ["そして、エイミーの音楽に一番大きな影響を与えたのが、", "お父さん方のおばあちゃんのシンシアだ"],
            "おばあちゃんのすすめで、週末は演劇の学校にも通い、歌やお芝居、タップダンスを習った":
                ["おばあちゃんのすすめで、週末は演劇の学校にも通い、歌やお芝居、", "タップダンスを習った"],
        }
        for body, expected in cases.items():
            self.assertEqual(wrap_body(body), expected)

    def test_fewest_lines(self):
        parts = wrap_body("そこで2008年2月10日、エイミーはロンドンのリバーサイド・スタジオから、中継で出演することになった")
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(len(p) <= 36 for p in parts))


class WrapScriptTest(unittest.TestCase):
    SCRIPT = (
        "魔理沙「短いセリフ」\n"
        "魔理沙「しかも世界中で大ヒットした代表曲は、『リハビリ施設には行かない』と言い張る歌なんだぜ」\n"
        "\n"
        "霊夢「へえ」\n"
    )

    def test_wrap_and_renumber(self):
        wrapped, mapping = wrap_script(self.SCRIPT)
        self.assertEqual(
            wrapped,
            "魔理沙「短いセリフ」\n"
            "魔理沙「しかも世界中で大ヒットした代表曲は、\n"
            "『リハビリ施設には行かない』と言い張る歌なんだぜ」\n"
            "\n"
            "霊夢「へえ」\n",
        )
        self.assertEqual(mapping, {1: 1, 2: 2, 3: 4})
        self.assertEqual(renumber("# メモ\n1: a\n3: b @へえ\n", mapping), "# メモ\n1: a\n4: b @へえ\n")

    def test_idempotent(self):
        wrapped, _ = wrap_script(self.SCRIPT)
        again, mapping = wrap_script(wrapped)
        self.assertEqual(again, wrapped)
        self.assertEqual(mapping, {1: 1, 2: 2, 4: 4})


if __name__ == "__main__":
    unittest.main()
