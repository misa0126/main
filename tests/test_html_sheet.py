import json
import re
import shutil
import subprocess
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
        self.assertEqual(first["images"], [{"no": 1, "ja": "甲子園", "en": "甲子園", "native": "", "caption": ""}])
        self.assertEqual(second["images"], [{"no": 2, "ja": "長崎", "en": "Nagasaki", "native": "", "caption": ""}])
        self.assertIn("<title>テスト 画像リスト</title>", html)

    def test_data_for_ymm4_placement(self):
        script = "魔理沙「一」\n霊夢「二の前半、\n二の後半」\n魔理沙「三」"
        html = build_sheet(script, "## a\n1: x\n3: y\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(data["utterances"], ["一", "二の前半二の後半", "三"])
        self.assertEqual([s["u"] for s in data["segments"]], [0, 1])
        self.assertEqual(data["lineU"], [0, 1, 1, 2])  # 画面で区切りを動かすときの、行ごとのセリフ番号
        self.assertIn('id="edit"', html)
        self.assertIn('id="ymm4"', html)

    def test_preloaded_images_by_number(self):
        # Claude が選んだ画像(001_ワード.jpg)を番号どおりに最初から入れておく。番号のない画像・範囲外は使わない
        tmp = Path(self.id().replace(".", "_") + "_imgs")
        tmp.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "001_甲子園.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "002_長崎.png").write_bytes(b"\x89PNGx")
        (tmp / "009_範囲外.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "メモ.jpg").write_bytes(b"\xff\xd8x")
        (tmp / "一覧.txt").write_text("x", encoding="utf-8")
        from material_collector.html_sheet import load_images
        html = build_sheet(SCRIPT, "## 導入\n1: 甲子園\n3: 長崎\n", "テスト", preload=load_images(tmp))
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        self.assertEqual(sorted(data["preload"]), ["1", "2"])
        self.assertTrue(data["preload"]["1"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(data["preload"]["2"].startswith("data:image/png;base64,"))

    def test_side_by_side_images(self):
        # 「A + B」は同時に横に並べる。「+3: C」は前の区切りの画像を出したまま、3行目から横に足す
        table = "## a\n1: 甲 @x + 乙 @y\n+3: 丙 @z\n"
        seg = parse_scene_table(table)[0]
        self.assertEqual([k.ja for k in seg["keywords"]], ["甲", "乙", "丙"])
        self.assertEqual(seg["joins"], [False, True, True])
        self.assertEqual(seg["ats"], [None, None, 3])
        html = build_sheet(SCRIPT, table, "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        images = data["segments"][0]["images"]
        self.assertNotIn("with", images[0])
        self.assertTrue(images[1]["with"])
        self.assertEqual((images[2]["with"], images[2]["at"]), (True, 3))
        with self.assertRaises(ValueError):
            parse_scene_table("## a\n1: 甲\n3: 乙\n+2: 丙\n")  # 区切りより前の行には足せない

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

    def test_caption_after_bar(self):
        html = build_sheet(SCRIPT, "## a\n1: 升田幸三 若い頃=young Kozo Masuda|升田幸三, 高野山=Mount Koya\n", "テスト")
        data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html).group(1))
        first, second = data["segments"][0]["images"]
        self.assertEqual((first["ja"], first["en"], first["caption"]), ("升田幸三 若い頃", "young Kozo Masuda", "升田幸三"))
        self.assertEqual(second["caption"], "")

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


class AquesTalkKanaTest(unittest.TestCase):
    def test_du_and_di_become_zu_and_ji(self):
        from material_collector.html_sheet import parse_yomi_table
        self.assertEqual(parse_yomi_table("1: ねばりづよい、ちぢむ。"), {1: "ねばりずよい、ちじむ。"})


class PatchHatsuonTest(unittest.TestCase):
    """YMM4の読みは「/」(抑揚)や数字のタグを残し、ちがうかなだけを直す(HTMLの中のJavaScriptを node で動かす)"""

    def run_patch(self, hatsuon, reading):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node がない")
        template = (Path(__file__).resolve().parents[1] / "material_collector" / "html_sheet_template.html").read_text(encoding="utf-8")
        start = template.index("function hiraOf")
        end = template.index("\n}\n", template.index("function patchHatsuon")) + 3
        code = template[start:end] + "\nconst a = JSON.parse(process.argv[1]); process.stdout.write(patchHatsuon(a[0], a[1]));"
        return subprocess.run(["node", "-e", code, json.dumps([hatsuon, reading])], capture_output=True, text=True, encoding="utf-8", check=True).stdout

    def test_vu_and_slash_before_small_kana(self):
        # 「ゔ」はゆっくりボイスが読めない。「じ/ょうじゅん」のように小さい字の前に「/」が残ると声が作られない
        out = self.run_patch("へびー/めたる/ばんど", "へゔぃめたるばんど")
        self.assertNotIn("ゔ", out)
        out = self.run_patch("せんきゅうひゃくきゅうじゅういちねん<NUMK VAL=12 COUNTER=がつ>じょう/じゅん", "せんきゅうひゃくきゅうじゅういちねんじゅうにがつじょうじゅん")
        self.assertNotRegex(out, r"/[ゃゅょぁぃぅぇぉっー]")

    def test_keeps_accent_marks_and_fixes_only_the_misread_word(self):
        self.assertEqual(
            self.run_patch("おおい/なか/しょうぎで、こま/どうしの/れんけいを/ねばりずよい", "おおいちゅうしょうぎで、こまどうしの、れんけいおねばりづよい。"),
            "おおい/ちゅう/しょうぎで、こま/どうしの/れんけいを/ねばりずよい",
        )

    def test_number_tags_become_the_table_kana(self):
        hatsuon = "<NUMK VAL=1952 COUNTER=ねん>からの<NUMK VAL=3 COUNTER=ねんかん>わ、めいじんと/おうしょうの_フたつの/たいとるを/も_チつずけた"
        self.assertEqual(
            self.run_patch(hatsuon, "せんきゅうひゃくごじゅうにねんからのさんねんかんわ、めいじんとおうしょうの、ふたつのたいとるおもちつづけた。"),
            "せんきゅうひゃくごじゅうにねんからのさんねんかんわ、めいじんと/おうしょうの_フたつの/たいとるを/も_チつずけた",
        )
        self.assertEqual(self.run_patch("しがつ<NUMK VAL=1 COUNTER=にち>に/しゅっぱつ", "しがつついたちにしゅっぱつ"), "しがつついたちに/しゅっぱつ")

    def test_name_reading(self):
        self.assertEqual(self.run_patch("ますだ/こうぞう、かどた/みつおと", "ますだこうぞう、かくたみつおと"), "ますだ/こうぞう、かくた/みつおと")
        # アクセント(')も残す
        self.assertEqual(self.run_patch("かどた'さんわ/き'た", "かくたさんわきた"), "かくた'さんわ/き'た")

    def test_english_words(self):
        # YMM4がかなにした英語の読みがちがうとき
        self.assertEqual(self.run_patch("あぷれ/の/しんさく", "あっぷるのしんさく"), "あっぷる/の/しんさく")
        # 英字のまま残っていたとき
        self.assertEqual(self.run_patch("iPhone/を/かった", "あいふぉんおかった"), "あいふぉん/を/かった")

    def test_uppercase_titles_read_as_words(self):
        # 大文字の曲名・本のタイトルを、YMM4が1文字ずつ読んでいたとき
        self.assertEqual(self.run_patch("えいちいーえるぴー/を/きいた", "へるぷおきいた"), "へるぷ/を/きいた")
        self.assertEqual(self.run_patch("ざ/ふぁーすと/えすえるえーえむ/だんく/が", "ざふぁーすとすらむだんくが"), "ざ/ふぁーすと/すらむ/だんく/が")
        self.assertEqual(self.run_patch("HELP/を/きいた", "へるぷおきいた"), "へるぷ/を/きいた")

    def test_uppercase_titles(self):
        # 大文字のタイトルを1文字ずつ読んでいたとき
        self.assertEqual(self.run_patch("える/おー/ぶい/いー/の/うた", "らぶのうた"), "らぶ/の/うた")
        # 大文字のまま残っていたとき(全角も)
        self.assertEqual(self.run_patch("HELLO/を/ききながら", "はろーおききながら"), "はろー/を/ききながら")
        self.assertEqual(self.run_patch("ＴＲＵＥ/の/かし", "とぅるーのかし"), "とぅるー/の/かし")

    def test_numbers_are_not_read_twice_and_commas_stay(self):
        hatsuon = "<NUMK VAL=1944 COUNTER=ねん><NUMK VAL=4 COUNTER=がつ>、<NUMK VAL=21 COUNTER=さい>の/おおやまの/もとに"
        self.assertEqual(
            self.run_patch(hatsuon, "せんきゅうひゃくよんじゅうよねんしがつ、にじゅういっさいのおおやまのもとに"),
            "せんきゅうひゃくよんじゅうよねんしがつ、にじゅういっさいの/おおやまの/もとに",
        )
        # 数字の読みが、前後の言葉と偶然ずれて合わさっても、タグを残して二重に読まない
        out = self.run_patch("<NUMK VAL=2 COUNTER=かい>めの/かいぎで、<NUMK VAL=1 COUNTER=にち>に/きまった", "にかいめのかいぎで、ついたちにきまった")
        self.assertNotIn("<", out)
        self.assertEqual(re.sub(r"[/、]", "", out), "にかいめのかいぎでついたちにきまった")
        self.assertIn("かいぎで、", out)


class ResizeVoicesTest(unittest.TestCase):
    """読みを直して拍の数が変わったセリフは、声の長さを読みに合わせて変え、後ろの物をずらす(ユーザーの指摘)。
    YMM4のセリフの長さには前後の間(息継ぎ)が入っているので、増えた・減った拍の分だけ変え、間は削らない"""

    PAD, PER_MORA, PER_PUNCT = 20, 6, 8

    def run_resize(self, items, fixes):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node がない")
        template = (Path(__file__).resolve().parents[1] / "material_collector" / "html_sheet_template.html").read_text(encoding="utf-8")
        start = template.index("const LETTER_MORA")
        end = template.index("\n}\n", template.index("function rippleItems")) + 3
        code = template[start:end] + (
            "\nconst a = JSON.parse(process.argv[1]); const items = a[0];"
            "const voices = items.filter(i => i.$type === 'V');"
            "const fixed = a[1].map(([k, b, f]) => ({ voice: voices[k], before: b, after: f }));"
            "fixed.forEach(f => { f.voice.Hatsuon = f.after; });"
            "const n = resizeVoices(items, voices, fixed);"
            "process.stdout.write(JSON.stringify({ n, items }));"
        )
        out = subprocess.run(["node", "-e", code, json.dumps([items, fixes])],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        return json.loads(out)

    def project(self, hatsuons, gap=0):
        """前後の間20フレーム、1拍6フレーム、句読点1つ8フレームで話すセリフを並べる(間 gap フレームずつ空ける)"""
        items, frame = [], 0
        for k, h in enumerate(hatsuons):
            body = re.sub(r"<[^>]*>", "", h)   # 数字のタグは、ここでは2拍ぶんの長さとみなす
            mora = len([c for c in body if c not in "、。？ぁぃぅぇぉゃゅょゎァィゥェォャュョ"]) + 2 * len(re.findall(r"<[^>]*>", h))
            punct = len([c for c in body if c in "、。？"])
            length = self.PAD + self.PER_MORA * mora + self.PER_PUNCT * punct
            items.append({"$type": "V", "CharacterName": "魔理沙" if k % 2 == 0 else "霊夢", "Hatsuon": h, "Frame": frame, "Length": length})
            items.append({"$type": "T", "Frame": frame, "Length": length})   # そのセリフの字幕・立ち絵
            frame += length + gap
        items.append({"$type": "BGM", "Frame": 0, "Length": frame})
        return items

    LINES = ["あいうえおかきくけこ", "さしすせそ、たちつ", "なにぬねのはひふへほまみ", "やゆよ、らりるれろ", "わをんあいうえ、おかき",
             "くけこさしすせそたちつてと", "なにぬね、のはひふへほ", "まみむめもやゆよ", "らりるれろわを", "あいう、えおかきくけ", "こさしす"]

    def test_shorter_reading_keeps_the_pause(self):
        # 「ティーエーアイジェーアイ」(10拍)を「たいじ」(3拍)に。前後の間は残り、話す部分だけ7拍ぶん短くなる
        items = self.project(["それじゃあ、こんかいわティーエーアイジェーアイのしょうがい"] + self.LINES, gap=4)
        old = items[0]["Length"]
        r = self.run_resize(items, [[0, "それじゃあ、こんかいわティーエーアイジェーアイのしょうがい", "それじゃあ、こんかいわたいじのしょうがい"]])
        v1, t1, v2 = r["items"][0], r["items"][1], r["items"][2]
        self.assertEqual(v1["Length"], old - 7 * self.PER_MORA)
        self.assertEqual(t1["Length"], v1["Length"])
        self.assertEqual(v2["Frame"] - (v1["Frame"] + v1["Length"]), 4)   # 次のセリフまでの間はそのまま

    def test_english_letters_left_in_reading_are_counted(self):
        items = self.project(["こんかいわTAIJIのしょうがい"] + self.LINES)
        old = items[0]["Length"]
        r = self.run_resize(items, [[0, "こんかいわTAIJIのしょうがい", "こんかいわたいじのしょうがい"]])
        # TAIJI = てぃー(3)えー(2)あい(2)じぇー(3)あい(2) = 12拍 → たいじ 3拍
        self.assertEqual(r["items"][0]["Length"], old - 9 * self.PER_MORA)

    def test_short_line_with_number_is_not_cut(self):
        # 「えっ、2歳で！？」: 前の読みが数字のタグで拍が数えられない。元の長さより短くしない
        items = self.project(self.LINES + ["えっ、<NUMK VAL=2 COUNTER=さい>で？"])
        k = len(self.LINES)
        old = items[2 * k]["Length"]
        r = self.run_resize(items, [[k, "えっ、<NUMK VAL=2 COUNTER=さい>で？", "えっ、にさいで？"]])
        self.assertGreaterEqual(r["items"][2 * k]["Length"], old)

    def test_long_number_reading_gets_pad_and_mora(self):
        items = self.project(self.LINES + ["<NUMK VAL=1923 COUNTER=ねん>"])
        k = len(self.LINES)
        r = self.run_resize(items, [[k, "<NUMK VAL=1923 COUNTER=ねん>", "せんきゅうひゃくにじゅうさんねん"]])
        # 前後の間20 + 13拍×6
        self.assertAlmostEqual(r["items"][2 * k]["Length"], self.PAD + 13 * self.PER_MORA, delta=2)

    def test_later_items_shift_and_bgm_stretches(self):
        items = self.project(["あいうえおかきくけこ"] + self.LINES)
        total = items[-1]["Length"]
        r = self.run_resize(items, [[0, "あいうえおかきくけこ", "あいうえおかきくけこさしすせそ"]])
        self.assertEqual(r["items"][2]["Frame"], items[2]["Frame"] + 5 * self.PER_MORA)
        self.assertEqual(r["items"][-1]["Length"], total + 5 * self.PER_MORA)

    def test_same_mora_count_keeps_length(self):
        items = self.project(["あいうえおかきくけこ"] + self.LINES)
        r = self.run_resize(items, [[0, "あいうえおかきくけこ", "あいうえおかきくけそ"]])
        self.assertEqual(r["n"], 0)


class AlignVoicesTest(unittest.TestCase):
    """「間をそろえる」: YMM4が書いた本当の声の長さ(VoiceLength)+セリフの後の間(AdditionalTime)で長さを直す"""

    def run_align(self, items, fps=60):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node がない")
        template = (Path(__file__).resolve().parents[1] / "material_collector" / "html_sheet_template.html").read_text(encoding="utf-8")
        start = template.index("function rippleItems")
        end = template.index("\n}\n", template.index("function alignVoices")) + 3
        code = template[start:end] + (
            "\nconst a = JSON.parse(process.argv[1]); const items = a[0];"
            "const voices = items.filter(i => i.$type === 'V');"
            "const r = alignVoices(items, voices, a[1]);"
            "process.stdout.write(JSON.stringify({ changed: r.changed, silent: r.silent.length, items }));"
        )
        out = subprocess.run(["node", "-e", code, json.dumps([items, fps])], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        return json.loads(out)

    def voice(self, frame, length, voice_length, cache="abc"):
        return {"$type": "V", "Frame": frame, "Length": length, "VoiceLength": voice_length, "AdditionalTime": 0.4, "VoiceCache": cache}

    def test_lengths_follow_real_voice_and_gaps_stay(self):
        items = [
            self.voice(0, 300, "00:00:04.5942500"),    # 本当は (4.59425+0.4)*60 = 299.66 → 300 のまま
            self.voice(300, 327, "00:00:04.5942500"),  # 見積もりで長すぎた → 300
            {"$type": "Image", "Frame": 300, "Length": 400},
            self.voice(627, 100, "00:00:02.0000000"),  # 本当は 144 → 長くする
            self.voice(737, 48, "00:00:00.4000000"),   # (0.4+0.4)*60 = 48 で合っている。前との間の10フレームはそのまま
            {"$type": "BGM", "Frame": 0, "Length": 900},
        ]
        r = self.run_align(items)
        v1, v2, img, v3, v4, bgm = r["items"]
        self.assertEqual(r["changed"], 2)
        self.assertEqual((v2["Frame"], v2["Length"]), (300, 300))
        self.assertEqual((img["Frame"], img["Length"]), (300, 373))    # 画像はセリフに合わせて縮む
        self.assertEqual((v3["Frame"], v3["Length"]), (600, 144))
        self.assertEqual(v4["Frame"], 600 + 144 + 10)
        self.assertEqual(bgm["Length"], 900 - 27 + 44)

    def test_voice_not_made_is_left_alone(self):
        items = [self.voice(0, 300, "00:00:00", cache=""), self.voice(300, 100, "00:00:02.0000000")]
        r = self.run_align(items)
        self.assertEqual(r["silent"], 1)
        self.assertEqual(r["items"][0]["Length"], 300)
        self.assertEqual(r["items"][1]["Length"], 144)


class VuTest(unittest.TestCase):
    def test_vu_becomes_ba_row(self):
        from material_collector.html_sheet import to_aquestalk_kana
        self.assertEqual(to_aquestalk_kana("へゔぃめたる、えゔぁんす、ヴォーカル、ゔ"), "へびめたる、えばんす、ぼーカル、ぶ")
