# Claude Code 向け常設指示

## 必ず守ること
- 作業を始める前に必ず `git pull` を実行する。このリポジトリは GitHub Actions が
  `drafts/` と `data/` を自動コミットするため、ローカルは常にリモートより古い前提
  で動くこと。
- push 前にも `git pull --rebase` してから push する。
- ユーザーはターミナル操作に不慣れなので、git 操作はユーザーに代行を求めず自分で
  実行する。

## このリポジトリについて
- Threads 自動投稿システム。GitHub Actions で朝10時に下書き生成、20時に投稿
  (月〜土、日曜休み)。
- 投稿の正は `drafts/YYYY-MM-DD.json`。Issue のコメントは生成時点の写しにすぎず、
  JSON を編集しても追随しない。
- 投稿失敗時は status が `failed` になる。Issue に `/approve` とコメントすると
  `approved` に戻る。

## 触ってはいけないもの
- `.env` は絶対に開かない、cat しない、内容を出力しない。
- トークンや API キーをチャットに表示しない。
