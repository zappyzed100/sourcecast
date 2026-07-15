# CLAUDE.md — guardrails-workbench

`upstream/` 配下は読み取り専用の submodule(参照元)。編集しない。

## UI スキル(`.claude/skills/` — ベンダー領域)

[.claude/skills/](.claude/skills/) は
[nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
からのベンダーコピー(オーケストレータ + サブスキル6つ)。**手で編集しない**。
出所 SHA と更新手順は [.upstream/sources.yaml](.upstream/sources.yaml)(id: ui-ux-pro-max-skill)が正本。

採用時の特別対応3点(2026-07-15 決定・経緯は sources.yaml の rationale)。
いずれも kit ブートストラップ時に**管理区画(`>>> GUARDRAILS BINDING >>>`)へ機械充填する**
(kit の `install_kit.py` は版上げ時に区画の中身を引き継ぐため、充填は更新で消えない):

1. **Python 実行**: `scripts/dev.py` の COMMANDS(加算形)へ次を充填し、
   スキル検索は `uv run scripts/dev.py design "<query>"` の動詞で呼ぶ
   (「Python は必ず uv 経由」kit GUARDRAILS §7.1。読み替え規約でなく動詞レールにする。
   uv 直呼びでの動作は確認済み):
   ```python
   COMMANDS.update({
       "design": [["uv", "run", "python",
                   ".claude/skills/ui-ux-pro-max/scripts/search.py", "{args}"]],
   })
   ```
2. **kit 検査の除外**: `scripts/repo_scan.py` の BINDING 区画へ次を充填する。
   `GENERATED_PATTERNS` は「手編集禁止・索引/検査から除外」の意味論で、内容系検査
   (ヘッダー必須・print 直呼び・ログ被覆・テスト非決定等)と STRUCTURE.md 索引の
   両方から外れる(check_structure.py は生成物を読み込まない)。
   gitleaks(秘密検出)は除外されない——それが正しい挙動:
   ```python
   GENERATED_PATTERNS += [re.compile(r"^\.claude/skills/")]
   ```
3. **生成物の扱い**: 同じ BINDING 区画へ次を充填する。`--persist` が書く
   `design-system/` はデザイン決定の記録としてコミット対象:
   ```python
   GENERATED_PATTERNS += [re.compile(r"^design-system/")]
   ```

emilkowalski/skills 由来の5スキル(アニメーション/デザインエンジニアリング系)は
`upstream/ui-skills/` の submodule 参照(ベンダーコピーではない)。repo_scan の列挙は
`git ls-files`(親リポジトリの追跡ファイルのみ)なので submodule の中身は最初から
検査対象外——特別対応は不要。
