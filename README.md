# Threads 自動投稿システム（現在は生成のみ自動・投稿は手動）

訪問看護ステーション向け Threads アカウントの投稿を、曜日別テーマに沿って
**週1回まとめて自動生成**し、GitHub Issue からコピペして毎日手動で投稿する
システムです。

> ⚠️ **投稿は現在手動運用です。** Threads APIのアクセスブロック
> （OAuthException code 200 "API access blocked"）が繰り返し発生したため、
> 自動投稿（`post.yml` の schedule）を停止しています。ブロックが解消すれば
> `post.yml` に schedule を戻すだけで自動投稿を再開できます（コードはそのまま
> 使えます。下記「自動投稿を再開する」参照）。

- 実行基盤: GitHub Actions（サーバー不要）
- 生成: Anthropic API（Claude）
- 投稿: 手動（Threadsアプリにコピペ）
- 運用: 週次まとめ生成 → GitHub Issue からコピペで毎日投稿 → `/posted` で記録

---

## 1週間の流れ

```
月曜 8:00 JST  週次の下書き生成ワークフローが動く
               └ その週の月〜土6日分をまとめて生成 → drafts/YYYY-MM-DD.json に保存
               └ 6日分が並んだ確認用 Issue が1本立つ（各日の本文・返信欄が
                 個別にコピーできるコードブロックになっている）

毎日 20:00     Issueから該当日の本文をコピー→Threadsアプリに貼り付けて投稿
               → 数秒後、返信欄をコピー→貼り付けて投稿
               → 投稿し終えたらIssueに「/posted 2026-08-24」とコメント
                 （日付省略時は当日扱い）

修正したい場合  drafts/YYYY-MM-DD.json を直接編集してからコピペする
               → 生成直後の本文と実際に投稿した本文が違えば、/posted 時に
                 その差分が style-notes.md に自動で追記される
               → 次回以降の生成プロンプトに、その傾向が反映されていく

日曜            生成も投稿もしない
```

---

## セットアップ

### 1. リポジトリを作る

このフォルダの中身をそのまま **プライベートリポジトリ** に push してください。

```bash
git init
git add .
git commit -m "初期構築"
git branch -M main
git remote add origin git@github.com:<あなた>/threads-auto-post.git
git push -u origin main
```

> ⚠️ 必ず **Private** にしてください。投稿履歴・ログが含まれます。

### 2. GitHub Secrets を登録

リポジトリの `Settings → Secrets and variables → Actions → New repository secret`

| 名前 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API キー |

モデルを変えたい場合は `Variables` タブに `ANTHROPIC_MODEL` を追加（既定 `claude-sonnet-4-6`）。

> `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` は今の運用（生成のみ自動・投稿は手動）
> では使いません。自動投稿を再開するときに登録してください（下記参照）。

### 3. Actions の書き込み権限を有効にする

`Settings → Actions → General → Workflow permissions` で
**「Read and write permissions」** を選択して保存してください。
（下書きやスタイルメモをリポジトリに自動コミットするために必要です）

### 4. 動作確認

`Actions → 下書き生成（週次） → Run workflow` を手動実行 → 6日分が並んだ
Issue が立てば成功です。

---

## ローカルでの操作

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY を記入

python -m src.cli check                            # 設定確認＋今週の状況
python -m src.cli generate-week                     # 今週(月〜土)の下書きをまとめて生成
python -m src.cli generate-week --monday 2026-08-24  # 対象週を指定
python -m src.cli generate --date 2026-08-24 --angle bonus --force  # 1日だけ作り直す
python -m src.cli show --date 2026-08-24            # 下書きを表示
python -m src.cli posted --date 2026-08-24          # 手動投稿の完了を記録
python -m src.cli log --limit 30                    # 投稿ログ（自動投稿再開後に使う）
```

テスト（API キー不要）:

```bash
python -m pytest tests -q
```

---

## 曜日別テーマ

| 曜日 | テーマ | 主な素材 |
|---|---|---|
| 月 | 給与・収入系 | 固定給45万円／賞与あり／固定給の安定性 |
| 火 | 職場リアル系 | 平均年齢30歳／相談しやすい文化／病棟との比較 |
| 水 | オンコール・夜勤系 | 一般スタッフは3か月に1回／夜勤手当／待機室 |
| 木 | 安定・環境系 | 都内廃業率6.9%／都内50店舗以上／勤務地が選べる |
| 金 | 休暇・ライフ系 | 有休消化率95%／10連休制度／1時間単位の時間休 |
| 土 | アカウント・DM誘導系 | 紹介制度のみ／働き方の選択肢／未経験歓迎 |
| 日 | — | 投稿なし |

素材や注意点を足したいときは **`src/themes.py`** を編集してください。
テキストを書き換えるだけで、次回の生成から反映されます。

### 自動チェックされる必須ルール

生成結果は保存前に自動検査され、違反があれば下書きと Issue に警告が出ます。

- **月曜**: 本文（1投稿目）に「45万」が含まれていないか
  → 金額は返信欄で明かすルールのため
- **水曜**: オンコール回数に「一般スタッフは」の断りがあるか
- 全曜日: 文字数（500字）、ハッシュタグの混入

警告が出た下書きは、コピペ前に `drafts/YYYY-MM-DD.json` を修正してください。

---

## 重複管理

`data/history.json` に「日付・テーマ・切り口・要約・つかみフレーズ」を記録します。

- 同じ切り口（例:「業界相場との比較」）は **28日間** 再利用しません
- **同じ週の6本の中でも**、切り口（angle_id）が重複しないように生成します
- 直近の投稿要約と使用済みつかみフレーズは、次回の生成プロンプトに渡され
  「これと被らないように」と指示されます
- 期間は `.env` または Secrets の `ANGLE_COOLDOWN_DAYS` で変更できます
- 重複管理の記録は `/posted` コメント時に行われます（投稿が実際に完了したときのみ）

切り口は `src/themes.py` の `angles` に自由に足せます。増やすほど重複しにくくなります。

---

## 文体メモ（style-notes.md）

`style-notes.md` には、これまでの手動修正から分かった文体の傾向をまとめています。
生成時にこのファイルの内容がプロンプトへ渡されるため、編集すれば次回の生成から反映されます。

ファイルは2つのパートに分かれています。

- **手書きの分析**（マーカーより上）: サンプルの少なさを踏まえ、「確認できた傾向」と
  「サンプル不足で判断できない点」を分けて書いています。断定できない内容を無理に
  一般化しないよう、必要なら手で追記・修正してください。
- **自動記録セクション**（`<!-- AUTO-EDITS:START -->` 〜 `<!-- AUTO-EDITS:END -->`）:
  `/posted` コメント時、生成直後の本文（`generated_body`/`generated_reply`）と
  実際に投稿した本文（`body`/`reply`）が違えば、その差分が自動で追記されます
  （直近15件まで。生の差分ログは `data/style_edits.jsonl` に全件残ります）。
  このセクションは自動生成なので、手で編集しても次の `/posted` で上書きされます。

---

## Issueコマンド

投稿確認用Issueで使えるコマンドです（コメントで実行）。

| コマンド | 効果 |
|---|---|
| `/posted [YYYY-MM-DD]` | その日の下書きを posted にし、history.json に記録する（重複管理に使われる）。日付省略時は当日 |
| `/reject [YYYY-MM-DD]` | その日は投稿しない扱いにする |
| `/approve [YYYY-MM-DD]` | 任意。承認の記録だけを残す（現在の運用では投稿の可否には影響しません） |

日付は省略するとコメント中の `/posted` などの直後、または当日として扱われます。

> **`/approve` について**: 以前は「承認しないと自動投稿されない」ゲートでしたが、
> 投稿自体が手動になったため、今は特に何もブロックしません。セルフチェックの
> 記録として使いたい場合のみ使ってください。使わなくても運用上の支障はありません。

---

## よくある運用

### 特定の日だけ作り直す

```bash
python -m src.cli generate --date 2026-08-24 --angle bonus --force
```

その週の該当ファイル（`drafts/2026-08-24.json`）だけ上書きされます。Issueの本文は
再生成しても自動更新されないので、コピペ時は最新のJSONファイルを見てください。

### 特定の日だけ休む

その日付で Issue に `/reject 2026-08-24` とコメントしてください（投稿予定から外れます。
実際にコピペしない、が唯一の強制力です）。

### 自動投稿を再開する

Threads APIのブロックが解消したら:

1. `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` を Secrets に登録
2. `.github/workflows/post.yml` に schedule トリガーを戻す
   ```yaml
   on:
     schedule:
       - cron: "0 11 * * 1-6"   # 20:00 JST 月〜土
     workflow_dispatch:
       ...
   ```
3. 必要なら `generate.yml` の週次生成頻度も元の毎日生成に戻す

投稿クールダウン（`src/guard.py`）・返信のみ再試行（`posted_partial`）の仕組みは
手動運用中も削除せずそのまま残しているので、再開時に手直しは不要です。

### トークンの更新（自動投稿再開時）

Threads の長期トークンは60日で失効します。

```bash
curl -s "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=<現在のトークン>"
```

返ってきたトークンを `THREADS_ACCESS_TOKEN` Secret に上書きしてください。

---

## 投稿ログ

`data/logs/YYYY-MM.jsonl` は自動投稿（`post` コマンド）が実行されたときのみ
記録されます。現在の手動運用では基本的に増えません（重複管理は
`data/history.json` と `/posted` コマンドで行われます）。

---

## ファイル構成

```
.
├── .github/workflows/
│   ├── generate.yml   月曜8:00 週次で下書き生成 → 1本のIssueにまとめる
│   ├── approve.yml    Issueの /approve /reject /posted を処理
│   └── post.yml       手動実行専用（schedule停止中）。自動投稿再開用に温存
├── src/
│   ├── config.py      環境変数・パス
│   ├── themes.py      曜日別テーマ・素材・切り口 ← よく編集する場所
│   ├── generator.py   Claude での生成＋ルール自動チェック＋style-notes.md読み込み
│   ├── weekly.py       週次まとめ生成（月〜土6日分、週内の切り口重複を回避）
│   ├── style_notes.py  手動修正差分を style-notes.md に自動蓄積
│   ├── threads_api.py Threads API クライアント（自動投稿再開用）
│   ├── history.py     重複管理（28日クールダウン＋週内重複回避）
│   ├── postlog.py     投稿ログ（自動投稿再開用）
│   ├── guard.py        投稿クールダウン（自動投稿再開用）
│   ├── drafts.py      下書きの読み書き
│   └── cli.py         コマンド
├── drafts/            下書き（YYYY-MM-DD.json）
├── style-notes.md     手動修正から分かる文体傾向（生成プロンプトに読み込まれる）
├── data/
│   ├── history.json       投稿済みネタの履歴
│   ├── style_edits.jsonl  手動修正の生の差分ログ（全件）
│   └── logs/               投稿ログ（自動投稿時のみ増える）
└── tests/
```
