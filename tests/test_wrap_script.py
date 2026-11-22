import unittest

from material_collector.wrap_script import renumber, split_serif, wrap_body, wrap_script


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

    def test_sentence_end_first(self):
        # 「！」「？」「。」の後ろで改行するのがいちばん(ユーザーの希望)
        self.assertEqual(
            wrap_body("子どもにそんな役目をさせるなんて！見張りじゃなくて、おやつを持たせてあげてほしいわ"),
            ["子どもにそんな役目をさせるなんて！", "見張りじゃなくて、おやつを持たせてあげてほしいわ"],
        )
        # 『』の中の「！」では切らない
        self.assertNotIn("『死ぬ！", wrap_body("霊夢はそのときの気持ちを、『死ぬ！もう無理！』と言いながら、何度も何度もくり返していた")[0][-3:])

    def test_fewest_lines(self):
        parts = wrap_body("そこで2008年2月10日、エイミーはロンドンのリバーサイド・スタジオから、中継で出演することになった")
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(len(p) <= 34 for p in parts))


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
        self.assertEqual(mapping, {1: [(1, 0)], 2: [(2, 0)], 3: [(4, 0)]})
        self.assertEqual(renumber("# メモ\n1: a\n3: b @へえ\n", mapping), "# メモ\n1: a\n4: b @へえ\n")
        # 横に足す画像の「+行:」も付け直す(半村良で付け直されず、区切りの順番が崩れた)
        self.assertEqual(renumber("1: a\n+3: b @へえ\n", mapping), "1: a\n+4: b @へえ\n")

    def test_idempotent(self):
        wrapped, _ = wrap_script(self.SCRIPT)
        again, mapping = wrap_script(wrapped)
        self.assertEqual(again, wrapped)
        self.assertEqual(mapping, {1: [(1, 0)], 2: [(2, 0)], 4: [(4, 0)]})


class SplitSerifTest(unittest.TestCase):
    LONG = "2007年3月12日には、アメリカの人気深夜番組、デイヴィッド・レターマンのショーで、ニューヨークの夜景を背に生のバンドと『リハブ』を歌った"

    def test_two_rows_max(self):
        # 3行になりそうなら、2行に収まる所の「、」でセリフを分ける(ユーザーの希望)
        parts = split_serif(self.LONG)
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(len(rows) <= 2 for rows in parts))
        self.assertTrue(parts[0][-1].endswith("、"))
        self.assertEqual("".join("".join(r) for r in parts), self.LONG)

    def test_script_and_reading_split(self):
        script = f"霊夢「へえ」\n\n魔理沙「{self.LONG}」\n"
        wrapped, mapping = wrap_script(script)
        self.assertEqual(
            wrapped,
            "霊夢「へえ」\n\n"
            "魔理沙「2007年3月12日には、アメリカの人気深夜番組、\n"
            "デイヴィッド・レターマンのショーで、」\n"
            "魔理沙「ニューヨークの夜景を背に生のバンドと『リハブ』を歌った」\n",
        )
        self.assertEqual(mapping[2], [(2, 0), (4, 3)])
        yomi = "1: へえ。\n2: にせんななねん、あめりかの、れたーまんのしょーで、にゅーよーくで。\n"
        self.assertEqual(
            renumber(yomi, mapping, reading=True),
            "1: へえ。\n2: にせんななねん、あめりかの、れたーまんのしょーで、\n4: にゅーよーくで。\n",
        )


class ReimuSentenceSplitTest(unittest.TestCase):
    def test_reimu_split_at_sentence_end(self):
        # 霊夢のセリフは「！」「？」「。」で 霊夢「」 を分ける(ユーザーの希望)。魔理沙はそのまま
        script = "魔理沙「すごいぜ！本当だぜ」\n\n霊夢「えっ！そんなことあるの？信じられないわ」\n\n霊夢「『死ぬ！』って言ったの」\n"
        wrapped, mapping = wrap_script(script)
        self.assertEqual(
            wrapped,
            "魔理沙「すごいぜ！本当だぜ」\n\n"
            "霊夢「えっ！」\n霊夢「そんなことあるの？」\n霊夢「信じられないわ」\n\n"
            "霊夢「『死ぬ！』って言ったの」\n",
        )
        self.assertEqual(mapping[2], [(2, 0), (3, 1), (4, 2)])
        again, _ = wrap_script(wrapped)
        self.assertEqual(again, wrapped)
        yomi = "1: すごいぜ。ほんとうだぜ\n2: えっ。そんなことあるの？しんじられないわ\n3: しぬ。っていったの\n"
        self.assertEqual(
            renumber(yomi, mapping, reading=True),
            "1: すごいぜ。ほんとうだぜ\n2: えっ。\n3: そんなことあるの？\n4: しんじられないわ\n5: しぬ。っていったの\n",
        )

    def test_english_title_not_broken_inside_word(self):
        # 「of th / e Firebird」のように英単語の途中で切らない(TAIJIの台本で起きた)
        text = "魔理沙「TSPのアルバム『The Last Resistance of the Firebird』が発売された」\n"
        out, _ = wrap_script(text)
        self.assertEqual(out, "魔理沙「TSPのアルバム『The Last Resistance of\nthe Firebird』が発売された」\n")
        self.assertEqual(wrap_script(out)[0], out)


if __name__ == "__main__":
    unittest.main()
