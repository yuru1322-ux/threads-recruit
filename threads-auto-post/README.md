# Threads 自動投稿システム

訪問看護ステーション向け Threads アカウントの投稿を、曜日別テーマに沿って自動生成し、
**確認・承認したうえで** 毎日20時（JST）に自動投稿するシステムです。

- 実行基盤: GitHub Actions（サーバー不要）
- 生成: Anthropic API（Claude）
- 投稿: Threads API（Meta 公式）
- 運用: 事前生成 → GitHub Issue で確認 → `/approve` → 20:00 に自動投稿

---

## 1日の流れ

```
10:00 JST  下書き生成ワークフローが動く
           └ Claude が本文＋返信欄を生成 → drafts/YYYY-MM-DD.json に保存
           └ 確認用の Issue が自動で立つ（本文がそのまま読める）

日中       Issue を見て確認
           ├ OK      → Issue に「/approve」とコメント
           ├ 修正    → drafts/YYYY-MM-DD.json を編集してから「/approve」
           └ やめる  → 「/reject」とコメント

20:00 JST  投稿ワークフローが動く
           ├ 承認済み  → 本文を投稿 →（数秒後）返信欄に続きを投稿
           │             履歴・ログを記録し、Issue に結果を返してクローズ
           └ 未承認    → 投稿せずスキップ（ログには残る）

日曜       生成も投稿もしない
```

**承認しないと投稿されません。** 承認を挟まず完全自動で回したい場合は
`post.yml` の `--require-approval` を外してください（下記「完全自動にする」参照）。

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

### 2. Threads API のトークンを取る

1. [Meta for Developers](https://developers.facebook.com/) でアプリを作成
2. 「Threads API」プロダクトを追加
3. 権限（スコープ）に **`threads_basic`** と **`threads_content_publish`** を追加
4. 自分の Threads アカウントを連携し、アクセストークンを発行
5. **長期トークン（60日）に交換**しておく

```bash
curl -s "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=<APP_SECRET>&access_token=<短期トークン>"
```

`THREADS_USER_ID` は次で確認できます。

```bash
curl -s "https://graph.threads.net/v1.0/me?fields=id,username&access_token=<トークン>"
```

> 📌 長期トークンも **60日で失効** します。切れる前に更新してください（下記「トークンの更新」）。

### 3. GitHub Secrets を登録

リポジトリの `Settings → Secrets and variables → Actions → New repository secret`

| 名前 | 内容 |
|---|---|
| `THREADS_ACCESS_TOKEN` | 上で取得した長期アクセストークン |
| `THREADS_USER_ID` | Threads のユーザーID（数値） |
| `ANTHROPIC_API_KEY` | Anthropic API キー |

モデルを変えたい場合は `Variables` タブに `ANTHROPIC_MODEL` を追加（既定 `claude-sonnet-4-6`）。

### 4. Actions の書き込み権限を有効にする

`Settings → Actions → General → Workflow permissions` で
**「Read and write permissions」** を選択して保存してください。
（下書きや投稿ログをリポジトリに自動コミットするために必要です）

### 5. 動作確認

`Actions → 下書き生成 → Run workflow` を手動実行 → Issue が立てば成功です。
その Issue に `/approve` とコメントし、`Actions → Threads投稿 → Run workflow` で
`dry_run: true` にして実行すれば、投稿せずに内容だけ確認できます。

---

## ローカルでの操作

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 各キーを記入

python -m src.cli check                    # 設定確認＋今週の状況
python -m src.cli generate                 # 今日の下書きを生成
python -m src.cli generate --date 2026-08-24 --angle before_after
python -m src.cli show                     # 下書きを表示
python -m src.cli approve                  # 承認
python -m src.cli post --dry-run           # 投稿せず内容確認
python -m src.cli post --require-approval  # 本番投稿
python -m src.cli log --limit 30           # 投稿ログ
```

テスト（API キー不要）:

```bash
python tests/test_basic.py
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

警告が出た下書きはそのままでは投稿せず、修正してから `/approve` してください。

---

## 重複管理

`data/history.json` に「日付・テーマ・切り口・要約・つかみフレーズ」を記録します。

- 同じ切り口（例:「業界相場との比較」）は **28日間** 再利用しません
- 直近の投稿要約と使用済みつかみフレーズは、次回の生成プロンプトに渡され
  「これと被らないように」と指示されます
- 期間は `.env` または Secrets の `ANGLE_COOLDOWN_DAYS` で変更できます

切り口は `src/themes.py` の `angles` に自由に足せます。増やすほど重複しにくくなります。

---

## 投稿ログ

`data/logs/YYYY-MM.jsonl` に1行1件で記録されます。

```json
{"logged_at":"...","posted_at":"2026-08-21T20:00:11+09:00","weekday":"金",
 "theme":"休暇・ライフ系","angle":"1時間単位の時間休という細かい制度",
 "body_text":"...","reply_text":"...","status":"success",
 "threads_post_id":"1789...","threads_reply_id":"1789...","error":null}
```

`status` の値: `success` / `failed` / `dry_run` / `skipped_not_approved` / `skipped_no_draft`

---

## よくある運用

### 完全自動にする（承認なし）

`.github/workflows/post.yml` の投稿ステップから `--require-approval` を消します。
下書きは10:00に生成され、20:00にそのまま投稿されます。
（生成を当日にせず前夜に回したい場合は `generate.yml` の cron を変えてください）

### 特定の日だけ休む

その日の Issue に `/reject` とコメントすれば投稿されません。

### 投稿時刻を変える

`post.yml` の cron（UTC）を編集します。`JST = UTC + 9時間`。
例: 21:00 JST にしたい → `cron: "0 12 * * 1-6"`

> ℹ️ GitHub Actions の schedule は、混雑時に **数分〜十数分遅れる**ことがあります。
> 秒単位の正確さが必要な場合は VPS の cron に移すことをおすすめします（コードはそのまま使えます）。

### トークンの更新

Threads の長期トークンは60日で失効します。失効すると投稿が失敗し、
Issue に `❌ 投稿に失敗しました` とコメントが付き、ワークフローも赤くなります。

```bash
curl -s "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=<現在のトークン>"
```

返ってきたトークンを `THREADS_ACCESS_TOKEN` Secret に上書きしてください。

---

## ファイル構成

```
.
├── .github/workflows/
│   ├── generate.yml   10:00 下書き生成 → Issue 作成
│   ├── approve.yml    Issue の /approve /reject を処理
│   └── post.yml       20:00 投稿 → ログ記録 → Issue に結果
├── src/
│   ├── config.py      環境変数・パス
│   ├── themes.py      曜日別テーマ・素材・切り口 ← よく編集する場所
│   ├── generator.py   Claude での生成＋ルール自動チェック
│   ├── threads_api.py Threads API クライアント
│   ├── history.py     重複管理（28日クールダウン）
│   ├── postlog.py     投稿ログ
│   ├── drafts.py      下書きの読み書き
│   └── cli.py         コマンド
├── drafts/            下書き（YYYY-MM-DD.json）
├── data/
│   ├── history.json   投稿済みネタの履歴
│   └── logs/          投稿ログ（月別 JSONL）
└── tests/test_basic.py
```
