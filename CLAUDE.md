# CLAUDE.md — guardrails-workbench

`upstream/` 配下は読み取り専用の submodule(参照元)。編集しない。

## UI スキル(`.claude/skills/` — ベンダー領域)

[.claude/skills/](.claude/skills/) は
[nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
からのベンダーコピー(オーケストレータ + サブスキル6つ)。**手で編集しない**。
出所 SHA と更新手順は [.upstream/sources.yaml](.upstream/sources.yaml)(id: ui-ux-pro-max-skill)が正本。

採用時の特別対応3点(2026-07-15 決定・経緯は sources.yaml の rationale):

1. **Python 実行**: スキル指示書内の `python3 scripts/...` は
   `uv run python .claude/skills/ui-ux-pro-max/scripts/...` に読み替えて実行する
   (guardrails-kit「Python は必ず uv 経由」規則との整合。uv 経由での動作確認済み)。
2. **kit 検査の除外**: guardrails-kit をブートストラップする際、`.claude/skills/` は
   ベンダー領域としてヘッダー必須・print 直呼び禁止・構造検査の対象から除外する
   (他人のコードに自リポジトリの規約を当てない)。
3. **生成物の扱い**: スキルの `--persist` が書く `design-system/` はスキル生成物として
   コミット対象にする(デザイン決定の記録)。kit ブートストラップ時に
   `GENERATED_PATTERNS` へ登録する。

emilkowalski/skills 由来の5スキル(アニメーション/デザインエンジニアリング系)は
`upstream/ui-skills/` の submodule 参照(こちらはベンダーコピーではない)。
