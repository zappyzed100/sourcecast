@AGENTS.md

# CLAUDE.md — Claude Code 固有の追記(規約の正本は AGENTS.md。本文を複製しない)

冒頭の `@AGENTS.md` が全エージェント共通規約(§0〜§13)を取り込む——Claude Code は
AGENTS.md を直読みしないため、このインポートが公式ドキュメント記載の到達経路
(.guardrails/GUARDRAILS.md §6。symlink 方式は Windows でプレーンテキスト化する罠があるため不採用)。

## Claude Code だけの追加の門(フック層 — .guardrails/GUARDRAILS.md §1・§2・§2b・§2c)
AGENTS.md の規則のうち以下は、Claude Code ではフックで**技術的にも**強制される
(他エージェントにこの層は無い——同じ規則が AGENTS.md §10-4 の心得＋commit/push/CI の門で効く):
- **編集直後の整形→lint**(§1): 自動で走る。lint の exit 2 は stderr の指摘を**その場で**
  直してから次へ進む(後回しにしても push 段で同じ違反に落ちる)。
- **迂回・作業消失の遮断**(§2): `--no-verify` / `SKIP=` / force push / `core.hooksPath`
  付け替え、および `.git` を含む `rm -rf`・dirty 時の `git reset --hard` 等は exit 2 で
  ブロック。通るかは実行前に `uv run scripts/dev.py probe "<cmd>"` で照会できる。
- **所有権ガード**(§2c): セッション開始時点で**人間の**未コミット変更があったファイルへの
  Edit/Write はブロック——人間が commit / stash するのを待つ(自動解除)。
- **ターン終了ゲート**(§2b): 未完了(未コミット作業 or `dev.py check` 赤)のまま
  ターンを終えると差し戻される。物理的ブロッカーは応答の先頭を `BLOCKED:` で始めて
  具体的に報告する。
