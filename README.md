# ゆっくり解説 素材自動収集ツール

台本テキストを渡すと、シーンごとにClaude APIでキーワードを抽出し、**ライセンスが確認できる画像サイト**から
候補画像を集めて自動選別するコマンドラインツールです。集めた画像は、Claudeが実際に見て台本の内容と合っているかを
チェックし、出典・作者・ライセンスを記録したクレジット一覧も自動で作ります。

## 取得元

上から順に探し、シーンごとの必要枚数に達したら終了します。

| 取得元 | 向いている素材 | APIキー | 扱い |
|---|---|---|---|
| Wikimedia Commons | 人物・史跡・歴史資料 | 不要 | ライセンス確認済み → `selected/` |
| Openverse | Flickrなどに公開されたCC画像(情景カット) | 不要 | ライセンス確認済み → `selected/` |
| メトロポリタン美術館 | パブリックドメインの美術品・肖像画 | 不要 | ライセンス確認済み → `selected/` |
| Pexels | 風景・物・雰囲気カット | `PEXELS_API_KEY` | ライセンス確認済み → `selected/` |
| Pixabay | 風景・物・雰囲気カット(日本語検索可) | `PIXABAY_API_KEY` | ライセンス確認済み → `selected/` |
| Google画像検索 | 上記で足りないときの補欠 | 不要 | **要確認** → `needs_review/` |

- ライセンス確認済みの取得元では、パブリックドメイン・CC0・CC BY・CC BY-SA・各サイト独自の商用可ライセンスだけを採用し、
  「非営利のみ(NC)」「改変禁止(ND)」は除外します。
- Google画像検索は「商用・改変可」のライセンス絞り込みをかけて検索しますが、判定は掲載ページの自己申告に頼るため、
  結果は `needs_review/` に分けて保存します。使う前に必ず出典を確認してください。`--no-google` で無効にできます。

## 重要: 権利に関する注意

- ライセンス情報は各サイトに登録された内容をそのまま使っています。登録内容自体が誤っている可能性はゼロではありません。
- CC BY / CC BY-SA の画像は、動画の概要欄などにクレジット表記が必要です。出力される `CREDITS.txt` を使ってください。
- **実在の人物(特に存命・最近亡くなった有名人)の写真**は、著作権とは別に肖像権・パブリシティ権の問題があります。
  ライセンスがCCでも、収益化動画での使い方によっては問題になり得ます。
- `needs_review/` の画像(Google検索結果)は権利未確認です。収益化チャンネルで使う場合は特に注意してください。
- 内容チェックはClaudeが出典のタイトル・説明と画像の見た目から判断するもので、顔で人物を特定するものではありません。
  人物の取り違えや年代のずれを見落とすことがあるため、投稿前に一度目で確認してください。

以上を理解した上での自己責任利用を前提としたツールです。

## HTMLの画像リスト(インストール不要)

台本と「区切り表」から、台本の順に番号を振った画像の検索リストをHTML1ファイルで作ります。

```bash
python -m material_collector.html_sheet scripts/nishizaki_yoshinobu.txt scripts/nishizaki_yoshinobu_scenes.txt --title 西崎義展
# → 西崎義展_image_list.html
```

- 区切り表は「## 話題の見出し」と「開始行: 画像1の日本語=英語, 画像2の日本語=英語, ...」の並びです(例: `scripts/nishizaki_yoshinobu_scenes.txt`)
- カンマで区切った1つが画像1枚で、台本の順に通し番号が付きます。外国の人物は「日本語=英語=母語」と書くと母語の検索ボタンも付きます
- 左に台本、右に番号ごとの検索ワードと「Google画像検索(日本語)」「Google画像検索(英語)」のボタンが並びます
- 貼り終わった画像には「済」のチェックを付けられます(ブラウザに保存)

## アプリで使う

1. このフォルダの `start_app.bat` をダブルクリックする(初回は準備に数分かかります。Pythonが入っていなければ自動でインストールします)
2. 「WindowsによってPCが保護されました」と出たら「詳細情報」→「実行」を押す
3. 「設定 → APIキーの設定」でClaude APIキーを入れる(Pexels / Pixabayのキーは任意)
4. 「台本」タブに台本を貼り付けて、タイトルを入れて「素材を集める」を押す
5. 終わると「確認シート」タブに、左に台本・真ん中にメモ・右に候補画像が並ぶ

### APIキーなしで使う場合

Claude APIキーがなくても、**キーワード表**を用意すれば素材集めができます(画像の内容チェックはなし)。
台本と一緒にキーワード表を作り(例: `scripts/miwa_akihiro_keywords.txt`)、アプリの「キーワード表」で選んでください。

```
# シーン番号: 日本語の検索語=英語の検索語, ...
1: 美輪明宏=Akihiro Miwa, シャンソン歌手=chanson singer stage
2: -          ← 画像を探さない(前のシーンの画像をそのまま使う)
3: 長崎 丸山=Maruyama Nagasaki, 出島=Dejima Nagasaki
```

コマンドラインでは `python main.py scripts/miwa_akihiro.txt --keywords scripts/miwa_akihiro_keywords.txt` です。

確認シートの画像は、そのままYMM4へドラッグするとファイルとして貼り付けられます。
右クリックで「画像をコピー」「フォルダで表示」「出典ページを開く」、クリックで拡大表示もできます。
結果は `ドキュメント/ゆっくり素材/<タイトル>_<日時>/` に保存され、「前回の結果を開く」でいつでも見直せます。

Macの場合はターミナルで `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python app.py` を実行してください。

## セットアップ(コマンドラインで使う場合)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # ANTHROPIC_API_KEY を設定
export ANTHROPIC_API_KEY=sk-ant-...
# 任意(設定すると取得元が増えます)
export PEXELS_API_KEY=...
export PIXABAY_API_KEY=...
```

## 台本フォーマット

シーンの区切りを **空行** で表します。

```
霊夢「今日は東京タワーについて解説するのよ」
魔理沙「東京タワーは1958年に完成した電波塔だぜ」

霊夢「高さは333メートルもあるのよ」
魔理沙「当時は世界一高い自立式鉄塔だったんだぜ」
```

上記は2シーンとして扱われます。サンプルは `examples/sample_script.txt` にあります。

## 使い方

```bash
python main.py examples/sample_script.txt -o output
```

人物解説の台本サンプルとして `scripts/miwa_akihiro.txt`(美輪明宏)も入っています。

主なオプション:

| オプション | デフォルト | 説明 |
|---|---|---|
| `-o, --output` | `output` | 出力先ディレクトリ |
| `--keywords-per-scene` | `3` | シーンごとに生成する検索キーワード数 |
| `--candidates-per-keyword` | `8` | キーワードごとにダウンロードする候補数 |
| `--images-per-scene` | `3` | シーンごとに最終選別する画像数 |
| `--min-width` / `--min-height` | `400` / `300` | 選別する画像の最小サイズ(px) |
| `--model` | Claude Haiku | キーワード抽出と内容チェックに使うClaudeモデルID |
| `--keep-candidates` | オフ | 選別前の候補画像もすべて保存する |
| `--sources` | `wikimedia,openverse,met,pexels,pixabay` | ライセンス確認済みの取得元(左ほど優先) |
| `--no-google` | オフ | 足りない分をGoogle画像検索で補わない |
| `--keywords` | なし | キーワード表を使う(APIキーなしでも動く) |
| `--no-relevance-check` | オフ | Claudeによる画像と台本の内容チェックを行わない |

## 確認シート(index.html)

実行が終わると出力先に `index.html` ができます。ブラウザで開くと、左に台本、真ん中にメモ(検索キーワード・
Claudeの判定理由・注意点)、右にシーンごとの候補画像が並びます。候補画像はそのままYMM4のタイムラインへ
ドラッグできます(Chrome / Edge推奨)。オレンジ枠は要確認の画像、「画像なし」のシーンは手動で探す必要があります。

## 出力構造

```
output/
  index.html             # 台本と候補画像を並べた確認シート
  manifest.json          # 全シーンの台本・キーワード・画像・出典・ライセンス・チェック結果の対応表
  CREDITS.txt            # 概要欄に貼れるクレジット一覧(ライセンス確認済みの画像のみ)
  scene_001/
    keywords.txt         # 生成された検索キーワード(日本語 / 英語)
    credits.txt          # このシーンのクレジット
    selected/            # ライセンス確認済みで選別された画像
      001.jpg
    needs_review/        # Google検索で補った要確認の画像(足りない場合のみ)
      001.jpg
    candidates/          # --keep-candidates 指定時のみ、選別前の全候補
  scene_002/
    ...
```

`manifest.json` には画像ごとに取得元・作者・ライセンス・元ページURL・内容チェックの判定理由が入っています。
内容チェックで落とされた画像も `rejected_by_relevance_check` に理由付きで残るので、判定が厳しすぎる場合の確認に使えます。

## 選別ロジック

1. 取得元のライセンス情報で、商用利用・改変ができないものを除外
2. 破損・読み込み不能な画像を除外
3. `--min-width` / `--min-height` 未満の低解像度画像を除外
4. 知覚ハッシュ(pHash)でシーン内の類似画像・重複画像を除外
5. Claudeが画像を見て、台本のシーンと内容が合わないものを除外
6. 優先度の高い取得元から `--images-per-scene` 枚に達するまで採用し、足りなければGoogle検索で `needs_review/` に補う

## テスト

```bash
python -m unittest discover -s tests -t .
```

## 制限事項

- 各取得元のAPIは無料枠の利用回数制限があります。大量のシーンを一度に処理すると、一時的に結果が返らなくなることがあります。
- Google画像検索の非公式スクレイピング(`icrawler`)を利用しているため、Google側の仕様変更で
  取得件数が減ったりエラーになったりすることがあります。
- 短時間に大量のシーン・キーワードを処理すると、Google側から一時的にブロックされる可能性があります。
