# .guardrails/CUSTOMIZE.md — 導入後にカスタムできる項目の索引

> **この文書は索引です。説明の正本は常に .guardrails/GUARDRAILS.md 側**——ここに書くのは
> 「何がカスタムできて、どこを見ればいいか」の1行ずつだけで、仕組みの説明は複製しません
> （複製は正本の分裂 — G5。Serena の `.serena/memories` を不採用にしたのと同じ理由）。
> ブートストラップが Step 10 まで完了したら、まずここを一読してください。

## 1. 数値・閾値の調整（列上書き可・すべて中立既定値）

科学的に確定した数字ではなく「妥当な出発点」です。プロジェクトの実態に合わせて変更してよく、
変更したら列の版を上げて記録します（`bindings/catalog.md` の運用ルール — G5）。

- コミットサイズの soft 上限・常時読込文書（CLAUDE.md/AGENTS.md）の行数上限・
  ログ境界検査の探索幅・複雑度ゲートの閾値 → .guardrails/GUARDRAILS.md §3.3・§3.4・§8.4、
  実体は `scripts/repo_scan.py` の該当定数

## 2. サンプル実装の差し替え

「貼り替え自由な出発点」として置かれているもの。中身を検査するのは門だけ
（存在検査のみ）——実装は自由に書き換えてよい。

- ログ単一出口（`logOp`/`log_op`） → .guardrails/GUARDRAILS.md §8.2・§8.4、実体は
  `bindings/catalog.md` の採用列の paste-block

## 3. トリガー待ちの機能（条件が来たら自分で有効化する）

まだ何も有効化されていない、意図的に寝かせてある機能の一覧です。

- 一覧とトリガー条件 → .guardrails/GUARDRAILS.md §10「保留（トリガー待ち）」節
  （例: GitHub Merge Queue・Context7・Chrome DevTools MCP・Serena・Skills化・
  Clean Room 隔離テスト・依存脆弱性監査 CI）

## 4. 規則の一時停止（既存コードへの導入・大規模是正時）

- `check_structure.py` の全 hard 規則は BINDING のパターンリストを空にすれば個別に
  止められる。ただし黙った停止は禁止——必ず .guardrails/GUARDRAILS.md §10 へ清掃 Phase として登録する
  → .guardrails/GUARDRAILS.md §11「既存リポジトリ向けの読み替え」・`PROMPT_claude_code_existing.md`

## 5. 個別の逃げ道（監査ログ付き。理由が必須）

- `RED-FIRST-EXEMPT: 理由` → .guardrails/GUARDRAILS.md §5
- `NO-LOG: 理由` → .guardrails/GUARDRAILS.md §8.4
- `NONDETERMINISM-EXEMPT: 理由` → .guardrails/GUARDRAILS.md §9.5（test-sleep/test-nondeterminism/
  test-network——非決定性の再現がテストの本質という正当なケース）
- `gitleaks:allow` → .guardrails/GUARDRAILS.md §3.1
- `install_kit.py --skip <パス>` → 既存ファイルを意図して維持する時

いずれも「使ってよいが、理由を書けば見える形になる」設計。レビューでは定期的に
使用頻度と理由の具体性を点検する（乱用監視）。

## 6. ツール・MCP の追加

- 既定は Playwright MCP のみ常駐。追加したい場合は採用ゲート3条
  （重複排除・常駐予算・契約整合）を通し、判定を記録してから
  → `bindings/catalog.md`「MCP・エコシステム採用規律」節

## 7. 規約文書そのものの編集

- `.guardrails/GOALS.md`・`.guardrails/GUARDRAILS.md`・`bindings/catalog.md` は編集してよい。ただし
  コミット本文に「どの G に効くか」の引用が無いと `governance-without-goal`
  検査で止まる → .guardrails/GUARDRAILS.md §3.4
