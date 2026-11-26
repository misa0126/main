import unittest

from material_collector.face_check import person_rows, split_names


class SplitNamesTest(unittest.TestCase):
    def test_two_japanese_names(self):
        self.assertEqual(split_names("山田康雄・納谷悟朗"), ["山田康雄", "納谷悟朗"])

    def test_foreign_name_is_one_person(self):
        self.assertEqual(split_names("リー・マーヴィン"), ["リー・マーヴィン"])
        self.assertEqual(split_names("モンキー・パンチ"), ["モンキー・パンチ"])

    def test_katakana_given_name_still_splits(self):
        self.assertEqual(split_names("清水マリ・堀絢子"), ["清水マリ", "堀絢子"])


class PersonRowsTest(unittest.TestCase):
    TABLE = """## a
1: いらすとや 退職=irasutoya retire @辞める
3: 小林清志 声優 写真=Kiyoshi Kobayashi @小林清志
## b
5: 根津 古写真=Nezu @根津
## c
7: 今井正 映画監督=Tadashi Imai|今井正 @今井正 + 山本薩夫 映画監督=Satsuo Yamamoto|山本薩夫 @山本薩夫
"""

    def test_picks_people_only(self):
        rows = person_rows(self.TABLE, "小林清志")
        self.assertEqual([(r["no"], r["names"]) for r in rows],
                         [(2, ["小林清志"]), (4, ["今井正"]), (5, ["山本薩夫"])])


if __name__ == "__main__":
    unittest.main()
