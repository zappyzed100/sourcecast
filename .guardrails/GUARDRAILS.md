# .guardrails/GUARDRAILS.md — LLMの作業出戻りを防ぐ仕組みの全体マップ

> **このファイルの役割**: リポジトリ全体に散らばっている「出戻り防止機構」
> （Claude Codeフック・pre-commit・CI・CLAUDE.mdの各種規則）を1箇所から見渡せるように
> した集約ビュー。**実装済み（✅）の機構については正本はこのファイルではない**——
> 各セクション末尾に挙げた実ファイルが常に最新かつ正しい。
>
> **実装状態の記号**:
> - ✅ = 実装済み。正本は実ファイル。本書は契約（呼び出し方・終了コード・保証）と所在のみ書く。
> - 🚧 = 未実装（契約のみ）。**コードが存在するまで、本書の該当節が唯一の正本**。
>   実装したら同一コミットで ✅ に更新する。実装順と完成条件は §10 のロードマップが正本。
>
> **本書が書いてよい範囲は「契約」まで**。各機構の *呼び出し方・終了コード・入出力・
> 保証すること*（＝インターフェース）は本書が規定する。*実装の中身*（正規表現の細部・
> 処理順など）は各スクリプト本体とその先頭ヘッダーコメントが正本であり、本書へは複製
> しない。契約と実装の食い違いを見つけたら、**同一コミットで両方を直す**。
>
> **ゲートは「わざと違反して落ちる」のを見届けて初めて完成**。fail-open（形だけ動いて
> 実は素通し）は静かに守りが消える最悪の欠陥——例: PreToolUse フックは exit 2 **以外**の
> 非0では何もブロックしない（§2）。だから §10 の全 Phase と §11 の全 Step の完成条件
> （DoD）には**違反注入テスト**を必ず含める。
>
> 本書は「言語非依存の契約（§1〜§9・§12）」と「言語固有の穴埋め」を分離してある。
> **穴埋めの正本は `bindings/catalog.md` の検証済み列**（運用は §12.7）——本書の中に
> 具象コマンド・正規表現が例として現れる場合、それは移植元の参照値であって正本ではない。
> この仕組み全体の**目標の正本は `.guardrails/GOALS.md`（G1〜G14）**——本書・キット・カタログへの
> 変更は、どのGに効くかを引用して初めて入れられる。
> **新規リポジトリへの移植は §11 のブートストラップ手順**で行う。
>
> 出戻り（rework）＝「後工程（コミット・push・CI）で初めて違反が見つかり、直してから
> 同じ作業をやり直す」こと。この仕組み全体の狙いは、違反の発見をできるだけ**前工程**へ
> 前倒しすること。

## 0. 全体像（タイミング × 検査 × 正本）

```
Edit/Write ─▶ [§1 整形→lint] ─▶ git commit ─▶ [§3 検査] ─▶ git push ─▶ [§4 検査+テスト] ─▶ CI [§5 全再実行+拡張]
                      （どの段の迂回も §2 が横断的にブロックする）
（この静的工程と直交して、開発ループ中は §12 のランタイム契約——共通動詞・操作/観察レール——が常時ある）
```

| タイミング | 何が動くか（節） | 自動修正 | 迂回可否 | 正本 |
|---|---|---|---|---|
| 編集直後（Edit/Write/MultiEdit / Codex apply_patch） | 採用列の整形→単一ファイル lint の**直列2段**（§1・v2.5） | 整形○／lint× | — | `.claude/settings.json` または `.codex/hooks.json` |
| `git commit` 時 | 衛生＋秘密検出＋STRUCTURE.md鮮度＋構造検査＋メッセージ検査（§3） | 一部○ | 禁止（§2で技術的にブロック） | `.pre-commit-config.yaml` |
| `git push` 時 | テスト＋静的解析（列充填）＋ブリッジ鮮度🚧（§4） | × | 禁止（§2） | `.pre-commit-config.yaml` |
| CI（PR・main push） | 上記すべて再実行＋E2E（列充填）＋red-first 証明（PR のみ・列充填・required — v2.9）＋カバレッジ計測🚧（§5） | × | 不可（リポジトリ側で強制） | `.github/workflows/guardrails-ci.yml` |
| ターン終了（Stop） | 未完了終了の差し戻しゲート（§2b。条件A=未コミット作業・条件B=構造検査が赤 — v2.9）——実行規律7の機械化 | × | —（fail-open＋回数上限） | `.claude/settings.json` または `.codex/hooks.json` |
| セッション開始→編集直前（SessionStart + PreToolUse Edit/Write/MultiEdit / apply_patch） | 所有権ガード（§2c・v2.6）——人間の未コミット変更の上書き防止 | × | —（fail-open＋表示） | `.claude/` または `.codex/` のフック |
| 開発ループ中（実行時） | 共通動詞 `dev.py`・操作/観察レール（§12） | — | —（未配線は明示エラー） | `scripts/dev.py`・`bindings/catalog.md` |

前工程に行くほど検査が軽く・速く、後工程に行くほど重く・広くなる設計
（`.pre-commit-config.yaml` 冒頭のコメント参照）。**各機構の実装状態の一覧は §10 の状態表が正本**。
外部語彙との対応: 世間のガイドで言う「Fail Loudly（静かに壊れず、派手に失敗して止まる）」は、
本キットでは §1 の exit 2 フィードバック・§2/§2b の fail-closed / fail-open 契約・§12.1 の
未配線明示エラーとして**実装済みの機構の別名**であり、新規項目ではない。

**初回セットアップ**: ① uv を公式インストーラで導入（マシンに1回） ②
`uv tool install pre-commit` ③ リポジトリで `pre-commit install` を1回実行。
以降、Python 系の実行・導入はすべて uv 経由（§7.1）。
`default_install_hook_types`（現在: `[pre-commit, commit-msg, pre-push]`）
に列挙されたフック種がまとめて入る。**フック種を増やしたら `pre-commit install` の再実行が必須**
——忘れると新フックは*静かに*無効なまま（fail-openの一種）。この取りこぼしは
§3.3 の `hook-type-missing`（hard）が機械検出する（心得を検査に変換 — G7/G9）。

**落ちた時の一次対応**（考え方の正本はルート `AGENTS.md` §10-4）:

| 症状 | 一次対応 |
|---|---|
| 衛生チェックで落ちた（§3.1） | 書き換えられたファイルを `git add` → 同じコミットを再実行 |
| gitleaks で落ちた（§3.1） | 本物の秘密→ファイルから除去して再実行（コミット前に止まるので履歴は無傷）。偽陽性→当該行に `gitleaks:allow` コメントを付けて再実行 |
| `generate-structure` で落ちた（§3.2） | `git add STRUCTURE.md` → 同じコミットを再実行 |
| `check-structure` の hard で落ちた（§3.3） | 出力の規則IDで §3.3 を引き、違反そのものを解消（自動修正はない） |
| `hook-type-missing` で落ちた（§3.3） | `pre-commit install` を再実行するだけ（フック種追加後の入れ忘れ） |
| `hooks-path-overridden` で落ちた（§3.3） | ユーザーの端末で `git config --unset core.hooksPath`（Claude Code からの解除は §2 がブロックするため人間の操作） |
| `guard-corpus-mismatch` で落ちた（§2） | 門番の改修が過去に塞いだ迂回を開け直している。guard 本体とコーパスの期待値を**同一コミット**で揃える（期待値の書き換えだけで黙らせない） |
| 編集直後 lint（§1 第2段）で exit 2 | stderr の指摘を**その場で**直す（次の編集で自動再検査）。「lint 未導入」表示は素通し＝push 段で回収される合図 |
| コミットメッセージ検査で落ちた（§3.4） | 形式を直す。「テスト無しの fix」なら回帰テストを同梱するか、テストで再現できない修正なら fix でなく chore/refactor を名乗る |
| `undeclared-dependency` で落ちた（§3.4 検査4） | 意図した追加なら本文に `依存追加: <名前> — 理由1行` を書いて再実行。意図しない追加（コピペ・ツールの副作用）ならマニフェストから外す |
| 作業消失ガードでブロックされた（§2） | 消してよい変更なら先に `git stash`（または commit）で退避してから再実行——クリーンなツリーでは同じコマンドが素通しになる。`.git` を消す操作は常時ブロック（人間の指示なら人間の端末で） |
| `deprecated-api` で落ちた（§3.3） | ラベルが示す**現行 API へ置き換える**（旧作法へ戻さない）。パターンの根拠・代替は採用列のカタログ注記——値を変えるなら版上げで還元（§12.7） |
| 所有権ガードでブロックされた（§2c） | セッション開始時点から**人間の**未コミット変更があるファイル。人間が commit / stash すれば自動解除（AI 側からの退避コマンドは §2 が別途ブロック——人間の操作を待つ） |
| `feat-without-plan` で落ちた（§3.4 検査5） | レイヤー直下に新規ディレクトリを作る feat: に設計根拠の差分が無い。根拠（1行でよい）を `plan.md` / `docs/plans/` に書いて同コミットへ含める。根拠を書けない構造変更なら feat でなく refactor / chore を名乗る（v2.8 で hard 昇格＝G14「意図の保存」——決定点①は案Aで確定 §10 Phase 19） |
| `red-first-green` でジョブが赤（§5） | 同梱テストが親コミットでも緑＝バグを再現していない。親で赤になるテストに直す。CI 上で赤にできない修正なら本文に `RED-FIRST-EXEMPT: 理由` を書く（**理由必須**——空は免除不成立。乱用はレビューで点検 — ルート AGENTS.md §8。v2.9 で required に確定） |
| `bootstrap-*` で落ちた（§3.5） | `false-done` = ✅ の主張が再実行検証に落ちた——状態を 🚧 に戻して再実装（完了=実行結果）。`order` / `multi-flip` = 番号順に1コミット1Stepで ✅ 化し直す。`demote` = ✅→— は禁止・やり直しは ✅→🚧。台帳の書式は .guardrails/BOOTSTRAP.md 冒頭の注記 |
| `mcp-not-allowed` で落ちた（§3.3） | `.mcp.json` に採用許可リスト外の MCP がある。常駐が本当に必要ならカタログの「MCP・エコシステム採用規律」（ゲート3条: 重複排除・常駐予算・契約整合）を通し、判定を記録して `MCP_ALLOWED_SERVERS` へ追加（2026-07-07 調査の再判定＝版上げ）。スポット用途なら `.mcp.json` に入れず `claude mcp add/remove` のタスク単位運用にする（§12.4） |
| Codex で作業する | 規約の正本はルート `AGENTS.md`（ネイティブ直読み — §6）。`.codex/hooks.json` を `/hooks` で信頼すると、編集直後・操作直前・ターン終了のフック層も有効。`apply_patch` はアダプタが対象パスを抽出する |
| Cline 等で作業する | 規約の正本はルート `AGENTS.md`（ネイティブ直読み — §6）。commit / push / CI の門は git フックなので同じに効く。フック層（§1/§2/§2b/§2c）は AGENTS.md §10-4 の心得と CI が代役 |
| ターン終了が差し戻された（§2b） | stderr の理由を見る: 未コミット作業（条件A）なら DoD を満たしてコミット、構造検査が赤（条件B — v2.9）なら文面の規則IDで §3.3 を引いて解消しコミット。物理的ブロッカーなら応答の先頭を `BLOCKED:` で始めて具体的に報告する |
| pre-push のテスト・analyze・clippy で落ちた（§4） | 違反を直す（`allow` / `ignore` の乱発で黙らせない） |
| ブリッジ鮮度で落ちた（§4）🚧 | 再生成された生成物をコミットに含めてから再 push |
| `dev.py` の動詞が「未配線」で落ちた | `bindings/catalog.md` の採用列の値を `scripts/dev.py` の COMMANDS へ充填（§12.1） |
| 同じフックが **2回連続** で落ちた | 機械的リトライをやめて原因調査に切り替える |

---

## 1. 編集直後（Claude Code / Codex PostToolUse フック）✅ — 整形→lint の直列2段（v2.5 で第2段を追加）

Codex は `.codex/hooks.json` の `PostToolUse` で同じフック本体を実行する。Codexの編集は
`apply_patch` として渡るため、`codex_hook_adapter.py` がパッチから対象パスを抽出して各ファイルへ
整形→lintを直列適用する。プロジェクトフックは `/hooks` でレビュー・信頼するまで実行されない。

- **`.claude/hooks/post_edit_format.py`（第1段・自動修正系。v2.24でPython化）** — Edit/Write/MultiEditの直後に走る。対象判定は
  編集されたファイルパスの拡張子 → `DISPATCH` 辞書引きで行い、**採用列の整形コマンド**を
  その場で当てる（`DISPATCH` の中身は `bindings/catalog.md` の paste-block を Step 0 で
  充填。整形は冪等であること。直接バイナリを叩く——npx/uvx 経由は避ける・§7.7）。
- **`.claude/hooks/post_edit_lint.py`（第2段・判定系 — Phase 12。v2.24でPython化）** — 整形の直後、同じ編集
  ファイルへ**単一ファイル lint** を当てる。違反は exit 2（stderr が Claude に渡る）——lint の
  初出地点が push 段（§4）から編集直後へ2段前倒しになり、「push で落ちて再試行」のループ
  1周が消える。責務境界: `--fix` 系（自動修正）は第1段の仕事、ここは判定のみ。全体
  typecheck・全体テストはここに入れない（§4 に残す——予算は下記）。ツール未導入・実行
  不能（eslint の設定不足等）は **stderr 1行の表示＋素通し**（exit 0。表示で「静かな不発」
  を防ぎつつ編集フローは止めない——ゲートではないこの層の fail-open 側の整理）。
- **実行順の保証（実装時確定 — Phase 12）**: Claude Code の公式仕様では**同一 matcher に
  複数フックを並べると並列・順序不定**。そのため2エントリ登録ではなく、`settings.json` の
  PostToolUse を「stdin を保持して整形→lint を順に呼ぶ **1コマンドの直列**」として配線する
  （整形が非0ならその exit で短絡・lint の exit 2 はそのまま伝播——実測で確認済み）。
  これにより順序が実行環境の仕様変更に依存しない。
- **狙い**: フォーマット崩れ・lint 違反の検出地点を「コミット時/push時」から「編集した瞬間」へ
  前倒しする。これが効いていれば後段のフォーマットチェックはほぼ常に素通りし、
  「コミットが落ちて再試行」というループ1周分が丸ごと消える。
- **終了コードの意味（Claude Code の仕様）**: PostToolUse はツール実行「後」に走るため
  編集自体は取り消せない。exit 2 のとき stderr が Claude に渡され自己修正の材料になる。
  それ以外の非0は非ブロッキング（表示のみで続行）。
- **性能予算**: 整形＋lint 合計で**編集1回あたり3秒以内**（§7.7・v2.5 新設）。予算に
  収まらない言語の lint は「該当なし（push 段で回収）」としてカタログに判断を記録する
  （dart-flutter@4・rust@4 がその例）。
- 正本: `.claude/settings.json` の `hooks.PostToolUse`（直列1コマンド）とスクリプト本体2つ。

## 2. 迂回防止（Claude Code / Codex PreToolUse フック + permissions）✅ — 横断的な防壁

Codex では `.codex/hooks.json` が Bash と `apply_patch` を対象にし、Gitルート基準のコマンドと
Windows用 `commandWindows` を持つ。Codexの PreToolUse は完全な強制境界ではなく、未捕捉のツール
経路があり得るため、commit/push/CI の門を最終防衛線として必ず残す。

出戻り防止の各種チェックは「迂回されたら意味がない」ため、迂回そのものを二重に塞ぐ。

- **`.claude/hooks/guard_git_bypass.py`**（PreToolUse: Bash・v2.23 で Python 化 — §7.7 Phase 33） — 実行されようとする Bash
  コマンド文字列に対し、`git commit`/`git push` で `--no-verify`（結合短フラグ含む別名 `-n` も）
  または `SKIP=` を伴うもの、`git push` の `--force`/`-f`（`--force-with-lease` 含む）、
  `core.hooksPath` の付け替え（フック本体の差し替え＝全フック迂回）、
  `pre-commit uninstall`（シムの取り外し。`uvx` 経由や `cd x && …` を含む）、および
  **`.git/hooks/` 配下のシムの改変/除去**（v2.46——`rm`/`mv`/`chmod`/`ln`/`tee`/`truncate`
  による削除・無効化、`> .git/hooks/…` の切り詰め。`pre-commit uninstall` の語を使わずに
  同じ全ゲート迂回を行う経路。参照 `cat`/`ls` と正規の `pre-commit install` は素通し）を
  **exit 2** でブロックする。v2.5 からは**作業消失ガード**（下記——非可逆な作業消失の防止）も同じ
  フック内の節として持つ（プロセス数を増やさない — G11）。deny（下記）は前方一致のみなので、**引数順・経由を変えた迂回を塞ぐのは本フックの責務**。引用符の中身（コミットメッセージ等）は判定前に
  取り除くため、メッセージ文面に `--no-verify` という文字列が入っていても誤検知しない。
- **PreToolUse の終了コード仕様（重要）**: ブロックするのは **exit 2 だけ**。exit 1 を
  含むその他の非0は「非ブロッキングエラー」でツールは実行されてしまう（fail-open）。
  したがってこのフック内の想定外エラーも exit 2 に倒す（fail-closed）ことが契約。
- **`.claude/settings.json` の `permissions.deny`** — 上記フックが万一漏れた場合の
  二重の防壁。`--no-verify` 付き commit/push・`--force` push・`core.hooksPath` の変更・
  `pre-commit uninstall`・`STRUCTURE.md` への直接 Edit/Write/MultiEdit を拒否する。
  🚧 Phase 6 で flutter_rust_bridge の生成物への直接 Edit/Write も追加する（§4）。
- 本節が塞ぐのは「迂回する操作」。**既に迂回された状態**（core.hooksPath が設定済み・
  シム未インストール）は §3.3 の `hooks-path-overridden` / `hook-type-missing` /
  `hooks-not-installed` が静的に検出する（操作の防壁と状態の検査で挟む — G7/G9）。
- **原則**: 「生成物は生成スクリプトだけが書く」。`STRUCTURE.md` を書いてよい主体は
  `scripts/generate_structure.py`（Bash ツール経由）のみ（§7）。
- ✅ **guard 迂回コーパス**（v2.4 — G10/G7/G11）: 主防壁の回帰テスト。
  `tests/guard_corpus.tsv`（1行 = `期待<TAB>コマンド` または `期待<TAB>前提<TAB>コマンド`・
  期待 ∈ DENY/ALLOW・前提 ∈ dirty/clean。空行・コメント行・書式不正は内部エラー＝
  コーパスが黙って痩せない）を
  `scripts/check_guard_corpus.py` が再生する——各行を PreToolUse と同じ形
  （`{"tool_input":{"command":…}}` の stdin JSON）で guard へ流し、exit 2=DENY /
  0=ALLOW を期待と照合。不一致は `HARD:guard-corpus-mismatch 行N: 期待X 実際Y: <cmd>`
  の1違反1行・exit 1、内部エラーは exit 2。**前提列（v2.5・Phase 14）**: 作業消失ガードの
  dirty 条件付き規則を再生するための列。前提付きの行は一時 git リポジトリ（dirty=未コミット
  変更あり / clean=変更なし）をカレントにして guard を呼ぶ——このとき外側の `GIT_*` 環境
  （フック実行中の git が設定する）と `CLAUDE_PROJECT_DIR` はフィクスチャ側へ差し替える
  （外のリポジトリ状態に判定が依存しない）。前提行が1行でもあれば git も必須になる。
  guard と再生器はPython標準ライブラリで動くため、jq・bashは不要。pre-commit では `files:` で
  門番3点（guard・コーパス・チェッカ）に限定して配線＝通常コミットでは走らず、門番に
  触れた時だけ回る。CI の `--all-files` では常時回る（二重の網）。門番の改修が過去に
  塞いだ迂回を静かに開け直す事故（門番自身の回帰）を、fix⇔テスト（G10）と同じ複利の
  型で機械停止する。予算: 全行10秒以内（§7.7・v2.22で実測是正）。
- ✅ **作業消失ガード**（v2.5・Phase 14 — G7/G9/G10）: 迂回とは別種の「exit 2 で止める
  価値が確実な操作」＝**非可逆な作業消失**を同じ主防壁で塞ぐ。汎用の「危険コマンド一覧」
  は採らない（誤検知の密集地帯——§7.4「近似は仕様」の精神で、確実な2種だけを対象にする）。
  - **常時ブロック**: `.git` を含む `rm -rf`（結合フラグ `-rf`/`-fr`/`-Rf` 等の近似。
    リポジトリ履歴＝全作業の非可逆な破壊。履歴ごと消えれば §2〜§5 の全機構も無力）。
    引用符で包んだ `.git` は精密経路の除去で消えるため、生コマンド側の引用付きトークンも
    併せて見る（過剰ブロック側）。分離フラグ `rm -r -f` は近似の範囲外——実測されたら
    コーパスと同一コミットで還元する。`.github` 等は語境界で除外済み。
  - **dirty 条件付きブロック**: `git status --porcelain` が非空（未コミットの作業がある）
    **かつ**それを消すコマンド——`reset --hard`・`clean` の force（`--force`/短フラグ `-f`）・
    広域の `checkout .` / `restore .`（`.` は当該サブコマンドの後の単独トークンのみ＝
    `git add .` 等では発火しない。`restore --staged .` はインデックス操作のみで作業ツリー
    無傷のため対象外、`--worktree`/`-W` を伴えば対象）——のとき exit 2。**クリーンなら
    同じコマンドは無害なので素通し**（dirty 条件が誤検知をほぼ消す）。status の判定不能
    （git 不在・リポジトリ外）はブロック側に倒す（fail-closed — 本節の契約）。
  - 対象外の境界: ローカルDBの破壊は対象外（`reset` 1発で戻る設計が §12.2 の前提——
    可逆）。ブランチ切替・ファイル単位の restore・`stash`・`clean -n` は正規経路として素通し。
  - ブロック文面は迂回系と区別した専用文（`block_loss`）: 退避の正規経路（commit/stash）と
    「人間の指示なら人間の端末で」を案内する。
- ✅ **probe（事前照会）**（v2.4 — G4/G12/G2）: 「このコマンドは許可されるか」を実行前に
  1コマンドで照会する: `uv run scripts/dev.py probe "<cmd>"`（§12.1 の第10動詞。実体は
  `check_guard_corpus.py --probe`）。出力は `ALLOW`（exit 0）または
  `DENY guard: <ブロック理由>`（exit 1）、exit 2 は内部エラーに予約。コーパス再生と
  **同一経路**で guard を呼ぶため、probe の判定 = 実際の PreToolUse の判定（LLM の
  「試して exit 2 で怒られる」1周を削る）。
- **外部裏書き（v2.4 注記）**: ① `permissions.deny` の不動作報告（`.env` への Read deny が
  無視される等）が外部で複数実測されており、「deny は前方一致の第二防壁・主防壁はフック」
  という本節の二重構造の設計判断を裏書きする。② CLAUDE.md の規則は公式に「影響であって
  強制ではない」とされ、プロンプト注入で上書きされた攻撃事例も報告されている——門を
  CLAUDE.md（心得）ではなくフック・検査側に置く本キットの構造の外部裏書き。
- 正本: `.claude/settings.json`・スクリプト本体・`tests/guard_corpus.tsv`・
  `scripts/check_guard_corpus.py`。

## 2b. ターン終了ゲート（Claude Code / Codex Stop フック）✅ — 実行規律7の機械化（v2.4）

§10 実行規律7「途中でターンを終えない」はキットで唯一、心得のまま残っていた規律
だった。本節がそれを門に昇格させる（枝番は Step 8b の前例——§3 以降の番号参照を壊さない）。

Codexは `.codex/hooks.json` から同等の `stop_incomplete_guard.py` を起動し、状態は
`.codex/session/` に分離して保存する。Codexには `stop_hook_active` が文書化されていないため、
アダプタがStopイベントでは再試行カウンタを有効にする。両実装は `CHECK_SCRIPTS` により
`dev.py check` と同じキット固有検査集合を実行する。

- **`.claude/hooks/stop_incomplete_guard.py`**（`settings.json` の `hooks.Stop`。v2.24でPython化）——
  応答終了時に発火し、**exit 2 で終了を差し戻す**（stderr が Claude に渡り、続行の
  指示になる）。差し戻し条件（**いずれかの理由 ∧ 免除なし** の時のみ）:
  **条件A（v2.4）** `git status --porcelain` が非空（未コミットの作業がある）。
  **条件B（v2.9・決定点②の強化案を確定 — Phase 20）** ツリーはクリーンだが
  `dev.py check` が exit 1 かつ出力に `HARD:`——「クリーンにさえすれば赤い検査を
  残して終われる」隙間（条件A単独の残余）を塞ぐ。
  **免除（両条件共通）** transcript 終端 50 行に `BLOCKED:` で**始まる**報告がある。
  これで規律7の正規出口——(a) DoD を満たしコミット済み**かつ**構造検査が緑、
  (b) 物理的ブロッカーの具体的報告（応答の先頭を `BLOCKED:` で始める）——だけが
  終了経路になる。
- **条件Bの縮退と性能（fail-open は本節契約の適用）**: 条件Bはクリーンな時だけ走る
  （ダーティなら条件Aが先に成立——毎ターンのコストは §7.7 の 2 秒予算＋uv 起動数十ms）。
  uv 不在・`scripts/dev.py` 不在は**表示1行で条件Aのみへ縮退**（静かな不発の禁止は
  表示で満たす——§2c と同じ整理）。check の exit 2（内部エラー）・`HARD:` 行の無い
  非0 は差し戻さない。ハングは Claude Code 本体のフックタイムアウトが殺す
  （kill = exit 2 以外 → 差し戻されない側に倒れる）。差し戻し文面には `HARD:` の
  先頭5行を同梱する（規則IDから §3.3 へ直行できる — G4）。
- **判定「免除」は先頭一致の近似（仕様——§7.4 の流儀）**: transcript の JSONL に対して
  `"BLOCKED:`（値の先頭）を探す。素の `BLOCKED:` を探すと、本フック自身の差し戻し文面
  （`BLOCKED:` の指示を含む）が transcript に載った時点で恒久すり抜けになるため。
- **ループ保護（二重・条件A/Bで共有）**: ① 入力 JSON の `stop_hook_active=true`（既に差し戻しで継続中）
  のとき、`.claude/session/<session_id>.stopcount` のカウンタで差し戻しを**最大3回**に
  制限（新しい停止連鎖＝`stop_hook_active=false` で数え直し。正規終了でカウンタ削除。
  `.claude/session/` は .gitignore 済み——追跡すると porcelain が恒常非空になり
  ゲートが誤発火する）。② Claude Code 本体側にも連続ブロックの安全上限がある
  （v2.1.143+・`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` で調整可）。
- **【契約の非対称——§2 と対で読む】** 本フックの想定外エラー（git 不在・transcript
  読取不能・カウンタ書込不能・JSON 不正等）は **exit 0（fail-open・差し戻さない）**。
  PreToolUse（§2）は fail-closed が正だが、Stop で fail-closed にすると壊れたフックが
  **セッションを終了不能にする**。まとめ: **§2 = fail-closed ／ §2b = fail-open ＋
  回数上限**。この向きの違いこそが両節の契約の核心であり、DoD の違反注入も逆向きに行う
  （§2 は「エラーでもブロックされる」を、§2b は「エラーでも通る」を実測する）。
- Claude Code / Codex **以外**の環境（生の API・他エージェント）では本ゲートは無く、
  §10 実行規律7 が引き続き心得として効く（規律の文言は §10 に残置）。
- 決定点②は v2.9 で強化案（条件B）に確定——記録と DoD は §10 Phase 20。
- 正本: `.claude/settings.json` の `hooks.Stop` とスクリプト本体。

## 2c. 所有権ガード（SessionStart + PreToolUse フック）✅ — 人間の未コミット変更を AI が上書きしない（v2.6）

人間と AI の変更が**同じファイルの同じ diff に混ざる**と、原因追跡（どちらの変更がバグを
入れたか）が構造的に不能になる。本節はセッション開始時点で既に dirty だったファイル
（＝人間の WIP）への AI の Edit/Write を物理的にブロックする。

Codexでは `apply_patch` が編集ツール名・パッチ本文が入力となるため、`.codex/hooks/codex_hook_adapter.py`
が追加・更新・**削除**の対象パスを取り出して同じ判定を適用する。削除も人間のWIPを失わせる
編集なので、整形/lintでは除外しつつ所有権ガードでは必ず対象にする。CodexのbaselineとStopカウンタは
`.codex/session/` に保存し、Claude Codeの `.claude/session/` と混ぜない。

- **`.claude/hooks/session_baseline.py`**（`hooks.SessionStart`。v2.24でPython化）——セッション開始時点の
  `git status --porcelain` のパス集合（未追跡 `??` を含む——人間の新規ファイルも WIP）を
  `.claude/session/<session_id>.baseline` へ保存する（**先頭1行は`# source=<値>
  ts=<UTC ISO8601>`のメタデータ（v2.29）**、以降1行1パス・リポジトリ相対。
  クリーン開始でも**空の baseline を必ず書く**——「不在（不明）」と「開始時クリーン
  （保護対象なし）」を後段が区別できるようにする）。SessionStart は exit 2 でも
  セッションを止めない仕様のため、保存失敗は stderr 1行の表示のみで進行する。
- **`.claude/hooks/guard_human_wip.py`**（PreToolUse: `Edit|Write|MultiEdit`）——ブロック
  条件は**両方**成立の時のみ: (A) 対象 `file_path` が baseline に含まれる、かつ
  (B) そのファイルが**現在も**未コミット。人間が commit / stash すれば (B) が外れて
  **自動解除**——解除用の特別経路を作らない。パスの正規化（絶対→相対・区切り差）は
  `git status --porcelain -- <path>` の出力がリポジトリ相対で返ることを利用して git に
  任せる（§7.2 の Windows 罠を自前で踏まない）。baseline の`#`始まりのメタデータ行は
  パス比較から除外する（session_baseline.py と対 — v2.29）。
- **対の完成（Phase 14 → 16）**: §2 の作業消失ガード（自分・人間の WIP を**消せない**）と
  本節（人間の WIP を**上書きしない**）で、「未コミット作業の保全」が消失・混入の両面から
  塞がれた。AI がブロックを退避コマンド（`reset --hard` 等）で回避しようとしても、
  dirty ツリーでは §2 が先にブロックする——二つの門は互いの逃げ道を塞ぐ配置。
- **【契約——§2b の仲間・§2 と逆向き】** baseline 不在（SessionStart 未発火・保存失敗）・
  git 不在などの想定外は**警告1行＋exit 0（fail-open）**。書き込み保護は利便との
  トレードであり、壊れたフックが全編集を止めてはならない。まとめ: **§2 = fail-closed ／
  §2b・§2c = fail-open ＋ 表示**（静かな不発の禁止は表示で満たす）。DoD の違反注入も
  §2b と同じく逆向きに行う（「エラーでも通る」を実測する）。
- **既知の限界（仕様）**: baseline はセッション**開始時点**のスナップショット。同一
  セッション内で人間が並行して編集を始めたファイルは守れない。porcelain のリネーム行は
  両側のパスを保存する近似・`core.quotePath` の引用表記（非 ASCII パス等）は近似の
  範囲外（§7.4「近似は仕様」——実測されたら両フックを同一コミットで直す）。
- **既知の限界（v2.29・実機事故から追記）**: `SessionStart` は1セッション1回のみでは
  ない——公式仕様の `source`（`"startup"|"resume"|"clear"|"compact"`）通り、compact
  （要約）でも再発火する。`session_baseline.py` はこれを見ずに毎回無条件で
  baseline を書き直していたため、compact 直前に AI 自身が書きかけだった未コミット
  ファイルが「人間の WIP」として焼き付き、以後そのファイルへの Edit/Write が誤って
  ブロックされ続ける事故が発生した。対策として `source == "compact"` の時は baseline
  に一切触れず即 return する（人間が新たに並行編集を始める余地の無い自動イベントの
  ため）。`"resume"`（日をまたぐ等、真に人間が触れた可能性がある）と `"clear"`・
  `"startup"` は従来通り baseline を取り直す。この対策は **session_id が compact を
  跨いで安定する**という前提に依存する（現行バージョンで実測確認済み。ハーネス側の
  将来変更で崩れた場合に備え、`source` が取得不能・想定外値の時は安全側＝従来通りの
  baseline 取得にフォールバックする）。
- guard_human_wip.py は §2 のコーパス再生の**対象外**（別フック・baseline という状態を
  持つ）。回帰は Step 4 の違反注入 DoD に加え、`scripts/check_ownership_guard.py`
  （§10 Phase 36）が複数手順のシナリオ再生で自動的に担保する。
- 正本: `.claude/settings.json` の `hooks.SessionStart` / `hooks.PreToolUse`
  （`Edit|Write|MultiEdit`）とスクリプト本体2つ。`.claude/session/` は .gitignore 済み（§2b と共用）。

## 2d. ハーネス前提コメントの検証根拠タグ（v2.29 新設・レビュー運用）

`.claude/hooks/*.py` のヘッダーコメントは、Claude Code ハーネス側の契約（フックの発火
条件・入力 JSON の項目・exit code の意味）を断定する記述を含む。今回の事故（本節
「既知の限界（v2.29）」）は、この種の断定（「SessionStart は1セッション1回のみ発火」）が
検証されないまま残り、実機で覆るまで誰も気づかなかったことが根本原因だった。

対策（`NO-LOG:`・`RED-FIRST-EXEMPT:` と同型の「存在検査のみ・理由必須・乱用監視は
レビュー」境界——機械強制はしない。ハーネス前提の断定を検査で拾う一般規則を書くのは
コストに見合わないため、レビューでの気づきを狙う軽量規約に留める）: ハーネスの挙動を
断定するコメントには `HARNESS-VERIFIED: <出典> <確認日>` を付す。出典は公式ドキュメントの
パス（例: `code.claude.com/docs/en/hooks.md`）。確認日が古い断定を見つけたら、ハーネスの
現行仕様と突き合わせて再確認すること（レビュー規約——ルート `AGENTS.md` §8 と同じ運用形）。
既存6フックのうち断定を含む箇所へ本コミットで遡及的にタグを付けた。

タグ付け作業そのものが早速1件、ドキュメントと実機の食い違いを検出した:
`stop_incomplete_guard.py` が読む `stop_hook_active` フィールドは、この確認時点の
公式ドキュメントの入力スキーマに**記載が無い**（Phase 11・v2.4 導入時の実機確認に
基づく前提のまま）。断定を全部「検証済み」と一括で塗るのではなく、確認できた部分
（exit code の効果・`session_id`・`transcript_path`）とできなかった部分を分けて
記録した——本規約の狙いは「確認済みに見せること」ではなく「確認できていない箇所を
可視化すること」にある。

## 2e. 脅威モデル（この門が対象とするもの・しないもの）（v2.35 明文化）

本キットの多層（編集直後→操作直前→commit→push→CI）が対象とするのは
**事故・怠慢・機会主義的な近道**——`--no-verify` を試す・テストを省く・完了と自称する・
規約を忘れる——であり、この範囲は全機構が違反注入で実測済み（§10 の各 Phase）。

**対象外（サーバー側の設定にしか置けない層）**: リポジトリへの書込権限を持つ
**敵対的エージェントの拘束**。境界の実体は具体的に2経路:

1. **オラクルの同時書換**: `guard_git_bypass.py` の骨抜き**単体**はコーパス再生
   （pre-commit と CI 両方で発火——§2）が「DENY 期待が ALLOW を返す」として検出するが、
   guard と `tests/guard_corpus.tsv` の期待値を**同一コミットで**書き換えれば機械では
   検出できない——コーパスがオラクルだから。「期待値の書き換えだけで黙らせない」（§0）は
   レビューの持ち場であり、機械の持ち場ではない。
2. **PR 内の workflow 自己改変**: required checks は PR ブランチ側の workflow 定義で
   実行されるため、`guardrails-ci.yml` のジョブを骨抜きにした PR は required を通過
   し得る。`missing-required` が守るのはファイルの**存在**まで。これを塞ぐのは
   サーバー側（rulesets の workflow 保護・CODEOWNERS で `.github/` にレビュー必須）のみ。

したがって README 等の「技術的ブロック」は、**現在のセッションの操作経路
（PreToolUse フック）に対しては真**だが、門の実装ファイルへの書込みには開いている
（存在の消失は `missing-required`・単体の骨抜きは guard-corpus が検出する——上記2経路が
残余）。キットが規定する防衛の最外周はリポジトリ設定（Step 9 ④ required checks——
v2.35 から check-bootstrap が実測検証 §3.5。Merge Queue は §10 保留）であり、
そこから先はホスティング側の領分。1行で固定する:
**この門が買うのは「機械検査可能な違反ゼロ」まで（Phase 28）——本節はその脅威モデル版で、
「善意を仮定しない」は買えるが「敵意への耐性」はサーバー側設定と人間レビューが買う。**

## 3. コミット時（pre-commit）

`.pre-commit-config.yaml` が正本。導入は §0 の初回セットアップ1回のみ。

### 3.1 衛生チェック（自動修正あり）✅ ＋ 秘密検出 ✅
- ✅ `trailing-whitespace` / `end-of-file-fixer` / `check-added-large-files`（1MB上限）/
  `check-yaml` / `check-toml` / `check-merge-conflict`——いずれも
  `pre-commit/pre-commit-hooks` の既製フック。**落ちてもファイルが書き換えられている
  だけなので、そのファイルを `git add` して同じコミットを再実行すれば通る**。
- ✅ **gitleaks**: 公式 pre-commit フック（`repo: https://github.com/gitleaks/gitleaks`、
  `rev` は固定して更新はコミットで行う）。ステージ済み差分から トークン・APIキー・秘密鍵の
  パターンを検出して exit 非0。**コミット前に止めることが最大の価値**——一度 push された
  秘密は履歴書き換え＋鍵ローテーションという最悪級の出戻りになる。偽陽性の許容は
  当該行への `gitleaks:allow` インラインコメントで行単位・目に見える形に限る
  （設定ファイルでのパス丸ごと除外は原則しない）。ルート `AGENTS.md` §7「秘匿」の
  コミット面を機械化するもの。ログ出力面の対策は §8。

### 3.2 STRUCTURE.md鮮度確認（`generate-structure`）✅（Python/uv 版）
`scripts/generate_structure.py`（**契約は §7**）が
実ファイル・実シンボルから `STRUCTURE.md` を毎回再生成する。内容に差分が出た場合、
pre-commit の「フックがファイルを変更したら失敗扱い」機構（§7.6）により **1回だけ**
失敗する（＝鮮度確認）。対応は `git add STRUCTURE.md` → 同じコミットを再実行、のみ。
**`STRUCTURE.md` は生成物なので手で編集してはいけない**（§2 の deny で技術的にも
ブロック済み）。

### 3.3 構造検査（`check-structure`）✅（Python/uv 版）
`scripts/check_structure.py` が実行する（契約は §7）。検査器はすべて同梱済みで、
（列充填で有効化）と付く規則は採用列のパターン充填（Step 0〜）により発火する。
**hard 違反が1つでもあれば exit 1**（コミット停止）、**soft は stderr に警告を出す
だけで exit 0**。自動修正はしない。出力は **1違反1行・先頭に規則ID**
（例: `HARD:layer-violation app/lib/x.dart:12 説明…`）——LLM が機械的に本書と
突き合わせて直せる形式にする。検出パターンの実体はスクリプトが正本、
**「何を検査するか」の一覧は本節が契約**。

**新しい規則を足す時のレシピ（登録先の唯一の一覧——v2.45・Phase 47 の是正）**: 規則1つの
登録先は最大5箇所に増えた。漏れの大半は機械が検出するが、書く手間の道しるべはここ1箇所:
① 検査の実装（check_structure / check_commit_msg）＋本節の契約1行
② `repo_scan.py` の `GATE_REGISTRY` に1行（漏れは `gates-registry-drift` が hard で検出）
③ 可能なら違反注入コーパスへ1ケース（`tests/injections/`——注入で再現できない規則は
   Phase 47 追記の対象外5分類へ理由を足す）
④ 列充填が要る規則はバインディング変数の新設＋カタログの列（`binding-dead-pattern` /
   `binding-dead-path` が取りこぼしを検出）
⑤ フィクスチャでの違反注入 DoD（新規則自体の初回実測——③のコーパスがあれば dod 実行が兼ねる）。

**hard（exit 1・コミット自体を止める）**:
- （列充填で有効化）`layer-violation` — レイヤー違反（表Bの LAYER_FORBIDDEN_IMPORTS が定義。移植元の例: `app/` が `engine/` を直接import、または `engine/` が `app/` を参照）
- ✅ `missing-required` — 必須ディレクトリ・必須ファイルの欠落（正本4文書＋規約2文書（AGENTS.md / CLAUDE.md — §6）に加え、
  防壁の実体——`.guardrails/BOOTSTRAP.md`（台帳 — §3.5）・`.pre-commit-config.yaml`・`.claude/` のフック6本と settings・`guardrails-ci.yml`・
  `scripts/` 9本・`tests/guard_corpus.tsv`・`.gitattributes`・`.python-version`——自体も
  対象。防壁が消える＝静かな fail-open の最悪形 — G7/G9）
- ✅ `agents-import-missing` — CLAUDE.md 冒頭の `@AGENTS.md` インポート行の欠落（v2.10・
  Phase 22。規約の正本は AGENTS.md——Claude Code はこの import 経由でのみ到達する。
  複製・同期スクリプトではなく「分割＋この存在検査」がドリフト防止の実体 — §6・G5）
  （`missing-required`(AGENTS.md/CLAUDE.md)・本規則は**キット原本自身**（`.guardrails-kit-source`
  マーカー在中のチェックアウト）では SOFT に降格——導入先の Step 1 未着手と構造上
  区別不能なため、配布物に複製されないマーカーで明示判定する。v2.14・Phase 27）
- ✅ `mcp-not-allowed` — プロジェクト正本（追跡された `.mcp.json`——basename 一致）に
  採用許可リスト（`repo_scan.py` の `MCP_ALLOWED_SERVERS`——中立既定値は playwright のみ
  ＝**2026-07-07 の MCP・エコシステム調査の判定**）外の MCP サーバーがある（v2.11・
  Phase 23。1サーバー1行。追加はカタログの「MCP・エコシステム採用規律」ゲート3条を
  通し判定を記録してから——G3/G5/G7。解釈不能な JSON は `SOFT:mcp-unparseable` で素通し。
  タスク単位のローカル追加（`claude mcp add`——保留の運用形）は追跡外＝対象外）
- ✅ `context-doc-too-large`（**soft**） — 常時読込の規約文書（ルート/フォルダ CLAUDE.md
  =200行・AGENTS.md=500行が中立既定。`repo_scan.py` の `CONTEXT_DOC_LIMITS`——列上書き可）
  の行数超過を警告（v2.17・Phase 28・調査③）。常時読込の行数はそのまま常駐コンテキスト
  （G3）。soft の理由: 正当に育つ文書であり、分割の判断は人間。この警告は **Skills 化
  保留（§10）のトリガー「常駐が問題化した実測」のセンサー**を兼ねる。
- ✅ `env-file-tracked` — 実値の入り得る `.env` 系ファイルの追跡を拒否（v2.18・Phase 29・
  調査④）。gitleaks（§3.1）は**内容**のパターン検査＝低エントロピーの実値は素通りし得る
  ため、**存在自体**を hard で塞ぐ。雛形（`.env.example` / `.env.sample` / `.env.template`
  ——`repo_scan.py` の `ENV_FILE_ALLOWED`・列 += 可）は除外。解消は `git rm --cached`
  ＋ .gitignore 追記＋**値は漏えい扱いでローテーション**。
- （列充填で有効化）`missing-log-coverage`（**soft**） — I/O・外部呼び出し・エラーハンドラ
  境界（`LOG_BOUNDARY_PATTERNS`——列充填。空なら不発）の前後 `LOG_BOUNDARY_WINDOW`
  行以内に、単一出口のログ呼び出し（`LOG_CALL_PATTERN`）か `NO-LOG: 理由` コメント
  （`NO_LOG_COMMENT_PATTERN`）のどちらも無い（v2.19・Phase 31・§8.4）。「重要度」は
  機械が判定できないため対象を客観的境界に絞り、理由の妥当性は検証しない存在検査のみ
  （RED-FIRST-EXEMPT と同じ「見えるようにするだけ」の境界 — G9）。
- （移植元の例）`missing-cxx-bridge` — cxxブリッジ（`cxx::bridge`）の欠落（この種の存在検査は REQUIRED_CONTENT_RULES として表B/列が定義する — §12.6）
- （列充填で有効化）`test-sleep` — テスト内の sleep 系（flakyの温床。移植元の例: `sleep` / `Future.delayed`。
  免除は `NONDETERMINISM-EXEMPT: 理由` コメント — §9.5・v2.25）
- （列充填で有効化）`test-nondeterminism` — テスト内の非決定入力（移植元の例: `DateTime.now()`・引数なし
  `Random()`・`thread_rng`・`SystemTime::now`。契約と代替手段は §9.2。免除は §9.5 と同じ）
- （表Bで確率的コンポーネント有の場合に有効化）`test-calls-solver-direct` — テストコードからのソルバー直呼び。
  テストは `solve_for_test` 相当のラッパー経由のみ（契約は §9.1）
- （列充填で有効化）`log-direct-call` — 採用列の単一出口以外での print 系直呼び
  （契約は §8.2。移植元の例: `lib/services/log.dart` 以外での `debugPrint` / `print`。
  `scripts/`・`.claude/hooks/`・`.codex/hooks/` は既定で除外——キット自身の出力契約
  （§3.3 の1違反1行・§12.1 の `[dev] 動詞:` 形式・フックの「exit 2 の stderr が
  Claude に渡る」ハーネス契約 §1/§2）が stdout/stderr 直書きを規定するため
  （フック2ディレクトリは v2.45・Phase 47 の充填実測で発見した自己偽陽性23件の是正）。
  除外の正本は `LOG_EXIT_PREFIXES`）
- （列充填で有効化。境界検査を持つ言語のみ）`missing-catch-unwind` — FFI 境界ファイルに `catch_unwind` が1つも無い
  （契約は §8.2）
- （列充填で有効化・表Bで確率的コンポーネント有の場合）`missing-property-test`（**soft**）
  — `SOLVER_DIRECT_CALL_PATTERNS` 充填済みなのに、テストのどこにも性質形テストの痕跡
  （`PROPERTY_TEST_MARKERS`——PBT ライブラリの import 等）が無い（v2.41・Phase 43。
  実例オラクルだけの検証は実装と欠陥を共有し得る——契約と限界は §9.6。存在検査のみ・
  質は検査しない。マーカー未充填のまま solver だけ充填した状態も警告＝静かな不発に
  しない — G9）
- （列充填で有効化）`test-network` — テストファイル内の外部I/O直呼び（HTTP・生ソケット等。
  契約は §9.5、パターンは採用列が定義。免除は §9.5 と同じ `NONDETERMINISM-EXEMPT:`）
- （列充填で有効化）`deprecated-api` — 世代交代した旧 API の使用（v2.6・Phase 15）。
  LLM が訓練カットオフの都合で書きがちな旧作法（例: python の `datetime.utcnow(`）を、
  プロンプト規則（心得）でなく列パターン（門）で封鎖する。**テスト内限定でなく全コード
  走査**（旧作法はどこに書かれても旧作法）。パターンと出典規律（①ベンダー公式 AI
  プロンプト ②公式非推奨告知のみ初期値・近似不能な構文世代は載せない）の正本は採用列の
  カタログ注記。唯一の除外はパターン定義の正本ファイル `scripts/repo_scan.py` 自身——
  定義・ラベルは禁止対象の**引用**であって使用ではない（違反注入で実測した自己偽陽性。
  `LOG_EXIT_PREFIXES` が scripts/ を除外するのと同じ境界の引き方）
- （列充填で有効化）`ui-missing-testid` — UI操作要素にテストID属性が無い（契約は §12.4。
  対象ファイル・要素・属性の正規表現は採用列が定義）
- ✅ `binding-drift` — バインディング刻印 `BINDING-SOURCE: 列ID@版` が対象ファイル間で不一致
  （契約は §12.7。言語なしで常時有効）
- ✅ `hook-type-missing` — `default_install_hook_types` にあるフック種のシムが `.git/hooks` に
  一部だけ無い（install 再実行忘れ＝静かに無効、の機械検出 — §0。CI ではスキップ）
- ✅ `hooks-path-overridden` — `core.hooksPath` が設定されておりシムが無効（全防壁の静かな
  迂回の静的検出。解除はユーザー端末で `git config --unset core.hooksPath` — §2 参照）
- ✅ `binding-dead-pattern` — 充填したパターン辞書のキー拡張子が CODE_EXTS /
  HEADER_REQUIRED_EXTS に無く、その検査が永久に不発（列充填の取りこぼし＝fail-open の検出）
- ✅ `gates-registry-drift` — 門の台帳（`repo_scan.py` の `GATE_REGISTRY`——§12.1
  `dev.py gates` の表示元）と検査器コードの不一致（v2.43・Phase 45）。2方向:
  検査器が emit する規則IDが台帳に無い（未登録）／台帳の強制対象区分のIDが検査器の
  どこにも現れない（幽霊規則）。台帳は「何ができるか」の発見導線であり、腐ると一覧が
  嘘をつく——STRUCTURE.md 鮮度検査（§3.2）の機能一覧版（G4/G9）
- ✅ `installer-token-drift` — **キット原本限定**（v2.38・Phase 41）: インストーラの検証条項
  （`PRECOMMIT_REQUIRED`・settings 系の判定文字列）がキット自身のローカルフック/フック
  ファイルに追随していない。導入済みリポジトリの更新はインストーラ再実行だが、
  .pre-commit-config.yaml / settings.json はトークン検証つき KEPT（既存維持）のため、
  条項から漏れたフックは**旧設定を KEPT のまま通って静かに届かない**（fail-open — G9。
  実例: ownership-guard / codex-hooks が2版の間漏れていた）。導入先では列フックが混ざり
  キットのフックを機械判別できないため原本側で堰き止める（kit-source-exempt と対称）

**soft（警告のみ・コミットは通る）**:
- ✅ 1ファイル500行超
- ✅ 1フォルダに `CLAUDE.md` 以外で7ファイル超（`scripts/` は例外で無制限）
- ✅ ファイル先頭の役割一行ヘッダー未記述・形式不正
- （列充填で有効化）選択したレイヤーのフォルダ `CLAUDE.md` の欠落
- ✅ どこからも import/use・mod されない孤立ファイル（対象範囲・抽出器は採用列の
  `ORPHAN_UNIVERSES` / `IMPORT_TARGET_EXTRACTORS` が定義。O(N²) 実装の禁止——§7.3）。
  ts-react-web 列の `_ts_import_targets` は元々 `^\s*(?:import|export)` で行頭アンカーして
  おり、動的 `import()` が式として行の途中に来る形（例: `lazy(() => import("./X"))`）を
  取りこぼしていた——Prettier が改行を入れるかどうか（変数名の長さ）という無関係な事情で
  検出結果が変わっていた（v2.31・G7で是正——行頭アンカーとは別に非アンカーの動的 import
  パターンを併用し、行中のどこにあっても拾う）。同時に `.d.ts` 環境宣言ファイル
  （`is_ambient_declaration`）を対象範囲から除外——import されずに tsconfig の include
  経由で自動的に効くファイルのため、孤立扱いにする母集団に含めるべきではなかった
- ✅ `binding-unstamped` — バインディング刻印が未設定（Step 0 で採用列を刻印するまでの
  注意喚起 — §12.7）。刻印が**一部ファイルのみ**の状態は `HARD:binding-drift` になる
- ✅ `hooks-not-installed` — pre-commit のシムが1つも無い（出荷直後〜Step 3 前の正常状態。
  一部だけ無い状態は `HARD:hook-type-missing`。CI ではスキップ）
- ✅ `binding-dead-path` — 充填したパス/prefix 型バインディング（`LOG_EXIT_FILES`・
  `FFI_BOUNDARY_FILE_PATTERNS`・`LAYER_FORBIDDEN_IMPORTS`・`PLAN_LAYER_ROOTS`・
  `ORPHAN_UNIVERSES`）が追跡ファイルに1件も一致せず、対応する検査が静かに不発
  （v2.32・Phase 38）。`binding-dead-pattern`（hard）が**充填時**の拡張子取りこぼしを
  見るのに対し、こちらは**充填後**のファイル移動・改名に値が追随していないドリフトを
  見る——`missing-catch-unwind` / `feat-without-plan` / `layer-violation` / `orphan-file`
  は対象0件になると無反応で fail-open（G9）。soft の理由: ブートストラップ途中
  （対象コードが未作成）の正当な一時状態と区別できない——`binding-unstamped` と同じ
  「見える猶予」

**出荷状態の想定出力**: v2キットを配置した直後の `check` は
`HARD:missing-required AGENTS.md`・`HARD:missing-required CLAUDE.md`・
`HARD:agents-import-missing`（いずれも雛形が `*.template` のため——Step 1 で解消）・
`SOFT:binding-unstamped`（Step 0 の刻印で解消）・`SOFT:hooks-not-installed`（Step 3 の
`pre-commit install` で解消）の**5件が出て exit 1 になるのが正常**。

**例外: キット原本自身のリポジトリ**（`.guardrails-kit-source` マーカー在中）は
Step 1 を未来永劫実行しない（実体化は導入先の仕事——原本は雛形のまま配布するのが正しい
状態）。上記5件のうち前3件は SOFT に降格されるため、原本リポジトリの `check` は
`SOFT:binding-unstamped`・`SOFT:hooks-not-installed`・`SOFT:missing-required`×2・
`SOFT:agents-import-missing` の**5件 SOFT で exit 0 になるのが正常**（Phase 27）。

### 3.4 コミットメッセージ検査（commit-msg ステージ）✅
`scripts/check_commit_msg.py`（§7.1・§7.2 の言語・Windows 規則に従う）。commit-msg
ステージのフックはコミットメッセージファイルのパスを引数1つで受け取る。
**導入時は `default_install_hook_types` に `commit-msg` を追加し、`pre-commit install` を
再実行すること**（§0 の注意——やらないと静かに無効）。

- **検査1（形式・`commit-msg-format`）**: ルート `AGENTS.md` §10 の規約
  `^(feat|fix|test|docs|refactor|chore): .+` に一致しなければ exit 1。
  `Merge` / `Revert` / `fixup!` / `squash!` で始まるものは素通し。
- **検査2（fix ⇔ 回帰テストの対・`fix-without-test`）**: メッセージが `fix:` で始まるとき、
  `git diff --cached --name-only` に採用列の `TEST_PATH_PATTERNS` に一致するテストが1つも
  無ければ exit 1。ルート `AGENTS.md` §8
  「一度直したバグは回帰テストに固定し fix と同コミット」の機械化。
  **逃げ道はプレフィックスの意味論で定義する**: テストで再現できない修正は
  fix ではなく chore / refactor / docs を名乗る。`SKIP=` は §2 が禁止している。
  なお同梱したテストが**親コミットで赤だった**か（＝バグを再現していたか）は commit
  段では検証できないため、CI の `red-first` ジョブが証明する（§5 — v2.7）。
  ステージ済み変更が**空**のとき（メッセージのみの `--amend` 等）は検査2〜4を素通しする
  ——`--no-verify` が §2 で技術的に禁止されている以上、既存コミットの文言修正には
  この正規経路が必要（無いと文言修正が構造的に不可能になる）。
  **`TEST_PATH_PATTERNS` が空なら不発**（v2.30・G7で是正——検査5〜8の兄弟検査と同型の
  「列充填で有効化」バイパス。元は検査2だけこれが欠けており、言語列を1つも選んでいない
  （`TEST_PATH_PATTERNS` 未充填の）リポジトリ、および言語なしで出荷される本キット原本
  自身で、`fix:` コミットが**原理上絶対に通らない**状態を放置していた。CI で
  `check-commit-msg` を実際に実行させて初めて実機で顕在化した — 下記「commit-msg
  系ゲートの CI 実効化」参照）。
  **インラインテストも「テスト同梱」に数える**（v2.39・G10で是正——§10 Phase 42）:
  テストを別ファイルでなく同一ファイル内に同居させる言語（例: Rust の
  `#[cfg(test)] mod tests`）では、パス判別（`TEST_PATH_PATTERNS`）だけだと実際に
  テストを同梱した `fix:` を誤ブロックする。採用列が `INLINE_TEST_PATTERNS`
  （拡張子→追加行パターン——正本は `scripts/repo_scan.py`）を充填していれば、
  ステージ済み diff の**追加行**への一致をパス一致との **OR** で「テスト同梱」と
  みなす。発火条件も「どちらかのスロットが充填済み」へ拡張（インラインのみの列でも
  静かに不発にならない——G9）。なおインラインテストは red-first（§5）の単独実行
  対象にはならない（rust 列の「単一テストファイル実行=該当なし」の既存判断のまま）。
- **検査3（governance-without-goal）**: ステージ済み変更に正本3文書
  （`.guardrails/GOALS.md`・`.guardrails/GUARDRAILS.md`・`bindings/catalog.md`）が含まれるとき、メッセージ本文に
  Gの引用（`G1`〜`G14`）が1つも無ければ exit 1。.guardrails/GOALS.md 運用ルール「どのGにも効かない
  変更は入れない」の機械化（心得→commit-msg フック — G5/G7）。`git commit -v` の
  切り取り線以降（diff）は本文とみなさない。
- **検査4（undeclared-dependency — v2.5・Phase 13）**: ステージ済み変更に**依存マニフェスト**
  （正本: `scripts/repo_scan.py` の `DEPENDENCY_MANIFESTS`——既定4種:
  `package.json`・`pyproject.toml`・`Cargo.toml`・`pubspec.yaml`。**basename 一致**なので
  モノレポのネストも対象）が含まれるとき、その依存セクションに **HEAD と比べて追加された
  名前**があれば、名前がメッセージに現れない限り exit 1
  （`依存追加: <名前> — 理由1行` を本文に書く）。ルート `AGENTS.md` §10「依存は増えて
  よいが、黙って増えてはならない」の機械化——fix⇔テスト（検査2）と同じ「意味論で塞ぐ」型。
  - **対象外の境界**: lockfile（`package-lock.json`・`uv.lock` 等——`DEPENDENCY_MANIFESTS`
    に載せない＝推移的更新は対象外）／**版の更新・削除のみ**（名前集合の差分に出ない）／
    HEAD の無い初回コミット／HEAD に無い**新規マニフェスト**（ファイル全体が diff で見える
    ＝「黙って」ではない）／解釈不能な構文（**警告1行で素通し**——行指向の自前抽出は
    近似、近似は仕様 — §7.4。tomllib は使わない＝Python 下限 3.10 を維持 — §7.1）。
  - 名前照合は大文字小文字と `-`/`_` を畳んだ集合差（PEP 503 相当の近似）、メッセージ
    照合は本文全体（コメント・切り取り線除外後）への大小無視の部分一致。1違反1行で
    `HARD:undeclared-dependency (<パス>)` を列挙する。
- **検査5（feat-without-plan — v2.6 soft 導入・v2.8 hard 昇格＝G14「意図の保存」）**:
  `feat:` がレイヤー直下（正本: `scripts/repo_scan.py` の `PLAN_LAYER_ROOTS`——
  **列充填。空なら不発**＝`layer-violation` と同じ「列充填で有効化」）に **HEAD に無い
  新規ディレクトリ**を作るのに、設計根拠文書（`PLAN_DOC_PATTERNS`——既定 `plan.md` /
  `docs/plans/`。置き場の規約はルート `AGENTS.md` §4）の差分がステージに無ければ、
  `HARD:feat-without-plan` を1ディレクトリ1行で列挙して exit 1。
  fix⇔テスト（検査2・G10＝回帰の複利）と対をなす「**意図の複利**」（G14）——新しい構造には
  設計根拠が同コミットで残る。**逃げ道の意味論は検査2と同一**: 根拠を書けない構造変更は
  feat を名乗らない（refactor / chore）。根拠は1行でもよい——塞がれるのは「黙って」だけ
  （検査4と同じ設計）。
  - 対象外の境界: HEAD の無い初回コミット（検査4と同じ）／レイヤー直下への**ファイル**
    直接追加（ディレクトリを作らない）／HEAD に既存のディレクトリへの追加／ステージ空。
  - 沿革: v2.6 で soft（表示のみ）導入 → **v2.8 で hard 昇格＝G14 新設**（決定点①を
    案Aで確定——同時改修3点セットの記録は §10 Phase 19）。

- **検査6（feat-without-test — v2.13・Phase 25・soft＝警告のみ・**列充填で有効化**——`TEST_PATH_PATTERNS`・`INLINE_TEST_PATTERNS` とも空なら不発）**: `feat:` が
  コードファイル（生成物・テスト除く）に触れるのに、テストの変更が1つも無ければ
  `SOFT:feat-without-test` を警告して**通す**（テスト同梱の判定は検査2と同一——
  パス一致とインライン追加行一致の OR・v2.39）。出典: 著名ワークフローの収斂
  （2026-07-07 調査②——Superpowers の test-driven-development は「実装前にテスト」を
  鉄則として強制する等）。fix⇔テスト（検査2・hard）の feat 版だが、テスト不要な feat
  （配線のみ・雛形生成・UI 微調整）が正当に存在するため **soft で観測から始める**
  （v2.6 の検査5と同じ導入経路。昇格トリガーは Phase 25）。
- **検査7（commit-too-large — v2.13・Phase 26・soft）**: 純変更行数（追加+削除。
  生成物と lockfile を除外——数え方の正本は `repo_scan.py` の `COMMIT_SIZE_SOFT_LIMIT`
  =既定 400 行・`LOCKFILE_NAMES`。列が上書き可）が上限を超えたら
  `SOFT:commit-too-large` を警告して通す。大きな塊は「どのゲートがどの変更を検証したか」
  を追えなくする——実行規律2（1機構=1PR）の一般開発版を可視化する（hard にしない理由:
  正当な大型コミット——初回移植・一括リネーム——が普通に存在する。soft の警告が
  分割の習慣を作る側に賭ける）。

- **検査8（test-shrink — v2.18・Phase 30・soft・列充填で有効化——`TEST_PATH_PATTERNS`
  が空なら不発）**: `fix:` / `feat:` でテストファイルが**純減**（削除行>追加行——numstat・
  バイナリ除外）なら `SOFT:test-shrink` を警告して通す。既存テストの弱体化（assertion 削除で
  緑にする）は**門を欺く最短路**であり、red-first（§5）が守る「新テストが親で赤」の外に
  あった空白（調査④ Clean Room QA の脅威モデル）。正当な整理が普通に存在するため soft——
  警告の常態化は保留「Clean Room 隔離テスト」のトリガー実測に当たる。

### commit-msg 系ゲートの CI 実効化 ✅（v2.30・G9・Phase 37）

上記の検査1〜8は `stages: [commit-msg]` のローカル git フックとしてのみ定義されており、
CI の `checks` ジョブ（`pre-commit run --all-files`、`--hook-stage` 未指定）では実行され
**ない**（pre-commit 本体の仕様——`--hook-stage` を明示しない限り commit-msg 段のフックは
走らない）。つまり、コントリビューターがローカルで `pre-commit install` していない限り、
G引用必須・fix⇔テスト・依存宣言・feat⇔plan の全 HARD 検査は**誰にも掛からない**——
`.guardrails/GUARDRAILS.md` §2c の compact 誤爆修正を実装する過程で実機発見した静かな穴
（本キット原本自身のこの working copy にも `pre-commit install` が未実行だった）。

対策: `scripts/check_commit_msg.py` に `--base <rev> [--head <rev>]` モードを追加した。
base..head の非マージコミット1つずつを、そのコミットを**今まさに作ろうとしている状態**
（`git worktree add <sha>` → `git reset --soft <sha>^` で HEAD だけ親へ戻す——index・
working tree はそのコミットのスナップショットのまま）で一時 worktree に再現し、単発形態
（commit-msg フック）と全く同じ関数（`main_single`）を検査ロジックの複製ゼロで再実行する。
CI 側は `guardrails-ci.yml` に `commit-msg-history` ジョブを追加し、`red-first` ジョブと
同じ形（`fetch-depth: 0`・BINDING 不要——git と python だけで完結）で
`uv run scripts/check_commit_msg.py --base "${{ github.event.pull_request.base.sha }}"`
を実行する。

このタイミングで、`fix-without-test`（検査2）に兄弟検査（5/6/7/8）と同じ
「`TEST_PATH_PATTERNS` 未充填なら不発」バイパスが欠けていたことも発覚した
（§3.4 検査2 参照。列を1つも選んでいないリポジトリ、および言語なしで出荷される
本キット原本自身で `fix:` コミットが原理上絶対に通らない状態を放置していた）——
CI 実効化の前に是正済み。

## 3.5 ブートストラップ監査（`check-bootstrap` — ✅ の再実行検証）✅ — 実行規律1〜4の機械化（v2.12）

§10 実行規律のうち 1〜4（順序・1Step=1コミット・完了=実行結果・虚偽✅の禁止）は、
Stop ゲート（規律7 — §2b）導入後も**心得のまま**残っていた——ブートストラップの ✅ が
自己申告だったため。本節がそれを門に昇格させる。

- **進捗の正本は `.guardrails/BOOTSTRAP.md`**（台帳。`missing-required` の対象・完了後も削除しない
  監査証跡）。状態 = 🚧 / ✅ / —（対象外。備考の理由必須）＋ Step 0 が確定する
  固有名詞リストC（Step 1・10 の残置 grep の機械入力）。
- **`scripts/check_bootstrap.py`**（pre-commit の `check-bootstrap`——`files: ^\.guardrails/BOOTSTRAP\.md$`
  で**台帳に触れたコミット＝✅ 化の瞬間だけ**発火・CI の `--all-files` では常時再監査＝
  guard-corpus と同じ二重の網）が4種を機械検査する:
  - `bootstrap-order`: ✅ は先頭からの連続でなければならない（— は理由付きで飛ばせる）
    ——規律1。
  - `bootstrap-multi-flip`: 🚧→✅ のフリップは**1コミットに1つ**（HEAD の台帳との diff で
    判定。まとめての完了報告は監査不能）——規律2。
  - `bootstrap-false-done`: **✅ の Step ごとに、検証可能なアサーションをその場で再実行**
    ——規律3・4 の核心。例: Step 1 = 章見出し14本・★/TODO/固有名詞Cの残置 grep、
    Step 2 = `generate_structure --check` の再実行、Step 4 = guard コーパス**全再生**、
    Step 5 = 形式違反メッセージの**注入のやり直し**、Step 10 = コード全ファイルの
    TODO grep。落ちた ✅ は「🚧 に戻して再実装」の指示付き1行（規律4の監査ルールの門化）。
    アサーションは「事後に再実行して検証できる形」に限る近似（§7.4）——実装の質までは
    保証しないが、**虚偽 ✅ と空実装は物理的に積めなくなる**。
    **Step 9 は外部設定まで実測する**（v2.35・Phase 40）: required checks への `red-first`
    登録はリポジトリ内のどのファイルにも現れない（required の完成はリポジトリ設定まで
    — §5）ため、`verify_required_checks` が `gh api` でルールセット（読み取り権限で照会可）
    と旧来ブランチ保護（404=保護なしの確定回答・403=照会不能を区別）の両系統を照会する。
    fail の向きは2段——**検証できて不在は失敗**（虚偽✅・fail-closed）、**検証不能**
    （GitHub 以外のリモート・gh 不在・オフライン・未認証）**は表示して素通し**
    （fail-open＋表示 — §2b と同じ契約。CI の再監査は checks ジョブの GH_TOKEN で認証）。
    **不在の断定は両系統の確定回答が揃った時のみ**（v2.36 是正——片系統が照会不能のまま
    断定すると、旧来保護だけに登録した採用先が CI で必ず偽赤になる: CI の GITHUB_TOKEN は
    旧来保護の照会が常に 403。CI 再監査で確定判定を得るには **rulesets 側での登録を推奨**）。
    強制最低線は **3コアジョブ**（`checks`・`red-first`・`commit-msg-history` ——
    v2.37 是正）: 「後2者はローカルでも走るから重複」はローカルフックが動く経路にしか
    成立せず、CI を最終防衛線とする主張（§5）の対象経路（Web 編集・フック未導入マシン）
    ではこの2ジョブが唯一の強制点——required でなければ赤のままマージできる。列固有の
    テスト/E2E ジョブは名前が列依存のため最低線に含めない（required 化は推奨）。回帰は
    `check_bootstrap.py --verify-scenarios`（全モック10本・pre-commit の
    `bootstrap-verify-scenarios` が本体変更時に発火）が固定する。
  - `bootstrap-demote`: ✅→— の変更禁止（証跡の消去）。✅→🚧 の差し戻しは正規経路。
- **進捗を強要する門ではない**（全行 🚧 の出荷状態では沈黙で通る）——「進める」側の規律は
  プロンプトと Stop ゲート（§2b）が担い、本節は「進んだという主張」だけを検証する。
  タイミングの網羅: ✅ 化コミットで pre-commit が即検証 → 以降のあらゆる PR で CI が
  全 ✅ を再監査（Step 0〜2 の門導入前区間も、Step 3 以降のコミットで遡って検証される）。
- 性能: 台帳に触れたコミットのみ発火のため、重いアサーション（--check・コーパス再生）を
  許容する（§7.7 の例外は guard-corpus と同じ整理）。

## 3.6 違反ログ（violation ledger）✅ — 門が止めた/警告した事象の機械記録（v2.34・Phase 39）

git 履歴は「通ったもの」しか残さない——門が**止めたもの**（HARD・guard の DENY）と
soft が**警告して無視されたもの**は、どこにも記録されず消える。soft→hard 昇格の判断
（前例: `feat-without-plan` の v2.6 soft → 数タスク実測 → v2.8 hard）に必要な
「偽陽性率・再発頻度の実測」が逸話頼みになるのはこの欠落が原因。

- **書き先**: `.guardrails/violations.jsonl`（1違反1行の JSONL・**gitignore 済みの
  ローカル telemetry**。追跡しない理由: コミットノイズ化と、機械記録に門の対象たる
  コミット経路で手が入る改変面を作らないこと。消して失うのは頻度データのみ＝
  いつでも剪定してよい）。
- **スキーマ**: `ts`（UTC ISO8601）/ `stage`（check-structure・commit-msg・guard）/
  `severity`（HARD・SOFT・DENY）/ `rule_id` / `location`。**message は記録しない**——
  記録するのは第1層（事実）のみで、意味づけ・要約は書かない。LLM の失敗要約を事実として
  蓄積する経路は §3.5 が塞いだ虚偽✅と同型の汚染（記録は機械・解釈は暫定・昇格は人間承認）。
- **書き手**: `repo_scan.append_violations`（check_structure・check_commit_msg 単発形態が
  呼ぶ）と `guard_git_bypass.py` の `record_block`（フックは依存ゼロが前提のため独立の
  最小実装——スキーマを変えるときは両方を同一コミットで揃える）。
- **記録しない境界**（偽計上の防止）: ① コーパス再生・probe
  （`GUARDRAILS_LEDGER_SUPPRESS=1` — 再生の DENY 期待行は「実際の迂回試行」ではない）
  ② commit-msg の履歴再検査（一時 worktree 内で走るため ledger ごと破棄される——
  過去コミットの再生を新しい事象として二重計上しない） ③ CI（記録はされるが
  チェックアウトごと破棄——集計対象はローカルの開発ループ）。
- **fail-open**: 記録は門の付帯機能——書き込み失敗で門の判定（exit code）を変えない。
  ただし黙らない（G9）: 失敗は `[violation-ledger] 記録失敗` の stderr 1行で見える。
- **§13 中央メモ禁止との関係**: 禁止対象は **LLM が書く知識メモ**（誤要約の蓄積経路）。
  本 ledger は機械が書くイベントログで、書き手に LLM の解釈が入らない——境界はここ。
- **集計は実装しない（判断ごと記録）**: 「30日で N 回」の閾値判定・昇格提案の自動化は
  解釈層であり門に入れない。集計はアドホック（jq / python 数行）で足り、読ませた上での
  昇格判断は人間が行う（.guardrails/GOALS.md 運用ルールの導入閾値を参照）。
- 正本: `scripts/repo_scan.py`（`append_violations`）・`.claude/hooks/guard_git_bypass.py`
  （`record_block`）・`scripts/check_guard_corpus.py`（抑止側）。

## 4. push時（pre-push）（列充填）＋拡張🚧

`stages: [pre-push]` のフック群。コミットのたびに重い検査を待たされるのを避けるため、
push 時に回す。フック自体の導入は §0 の `pre-commit install` に含まれる。
正本: `.pre-commit-config.yaml`。

- **テスト・静的解析**: 採用列の pre-push フック群（`bindings/catalog.md` の paste-block を
  Step 0 で BINDING 領域へ充填。v2キットの出荷状態は空＝Step 6 までに必ず立てる。
  コードよりゲートが先）。CI で初めて赤くなる型・lint エラーを push 時点に1段前倒しし、
  §8.1 の lint 昇格（print禁止等）の発火点もここに置く。
- **生成ブリッジ鮮度（該当構成のみ）**: コード生成を使う構成では、採用列に再生成コマンドと
  生成物パスを追加し、push段またはCIで「再生成後に差分ゼロ」を検査する。キット共通の
  規約には特定のブリッジ実装を埋め込まない。

## 5. CI（GitHub Actions・最終防衛線）✅＋拡張🚧

`.github/workflows/guardrails-ci.yml`。ローカルのgitフックは原理的に迂回できる（別マシン・
`--no-verify` 等）ため、PRとmainへのpushで同じ検査を必ず再実行する。

- ✅ **`checks` ジョブ**: `pre-commit run --all-files`——pre-commitと全く同じ定義を
  そのまま再実行する（`.pre-commit-config.yaml` が唯一の定義元で、ローカルとCIの検査
  内容がドリフトしない設計）。フックによるファイル変更（＝§3.2 の再生成差分を含む）も
  CI では失敗として現れる。なお `pre-commit run` は既定で pre-commit ステージのフック
  のみ実行し、`stages: [pre-push]` の群は対象外のため、それらは下記の独立ジョブで
  明示的に回す。ジョブ冒頭の公式 setup-uv action が uv を保証する（§7.1。
  `.python-version` に従い Python 自体も uv が自動解決）。
- **言語別テスト・解析ジョブ**: 採用列の paste-block（`bindings/catalog.md`）を BINDING 領域へ
  貼る。v2キットの出荷状態は `checks` ジョブのみ（言語なし）。
- **`e2e` ジョブ（列充填）**: §12.4 の操作レールを PR の赤/緑へ変換する。完成条件は
  「E2E を1本わざと壊した PR が赤」（Step 8b の DoD）。
- ✅ **`red-first` ジョブ（PR のみ・列充填で有効化 — v2.7・Phase 18）**:
  `scripts/check_red_first.py` が PR 範囲（base..head・マージ除外）の `fix:` コミット毎に、
  そのコミットで**追加**されたテストファイル（`TEST_PATH_PATTERNS`）を親コミットの
  一時 worktree へコピーし、採用列の「単一テストファイル実行」
  （`repo_scan.py` の `SINGLE_TEST_COMMAND` / `SINGLE_TEST_CWD`——None なら不発＝
  言語なし出荷と両立）で1ファイルずつ実行する。**少なくとも1つが赤**（非0）なら
  証明成立、全部緑なら `red-first-green` を1コミット1行で報告——検査2（fix⇔テスト対
  — §3.4）の「同梱」を「バグを再現していた証明」まで引き上げ、「直した証明」を
  自己申告から実行結果に変える（G10/G7）。
  - **逃げ道の意味論は検査2と同一**: CI 上で赤にできない修正はコミット本文の
    `RED-FIRST-EXEMPT: 理由` 行で免除する（接頭辞は増やさない——形式規約 §3.4 検査1 を
    守る。免除・対象外はいずれも1行で見える＝静かなスキップの禁止）。
  - **導入強度は required（v2.9・決定点③を確定 — Phase 21）**: 違反は
    `HARD:red-first-green`＋exit 1 でジョブが赤。仕上げはブランチ保護の required checks へ
    本ジョブを登録する（リポジトリ設定——Step 9 ④）。確定の運用条件だった
    **`RED-FIRST-EXEMPT` の乱用監視**は二層で実装: 機械部分＝**理由の無い免除は不成立**
    （通常判定を続行——1行で見える）、人間部分＝レビュー規約（ルート AGENTS.md §8——
    理由の具体性・CI 上の再現不能性・頻度を点検）。表示のみへ戻すロールバックは CI の
    呼び出しに `--soft` を足すだけ（違反は SOFT: 列挙・exit 0。内部エラーの exit 2 は
    どちらのモードでも素通しにしない。ジョブサマリの赤/緑は両モード共通）。
  - **対象外の境界（1行表示・違反にしない）**: 追加テストの無い fix（既存テストへの
    追記は単離できない——同梱自体は検査2が担保済み）／`SINGLE_TEST_CWD` の配線外の
    テスト（単一スロット＝複数言語構成の副言語側）／親の無い初回コミット・親に実行
    ディレクトリが無い場合。
  - **近似は仕様（§7.4）**: 「非0 = 赤」。親で実行エラーになるテスト（fix と同時に
    足したヘルパへ依存する等）も赤と数える——親が fix を欠く事実の現れとして寛大側に
    倒す。ハングは赤の証明にならないため内部エラーで止める（1テスト 300 秒の保険）。
  - exit 契約: 0=違反なし（`--soft`・不発・fix なしを含む）／1=違反あり（`--soft` では
    返さない）／2=内部エラー。呼び出し・worktree の位置・トークン展開の詳細は
    スクリプト先頭ヘッダーが正本（§7 の流儀）。
- **E2E・カバレッジ・ツールチェーン（列充填）**: 対象プラットフォームのE2E、表示から始める
  カバレッジ、言語ランタイムやネイティブ依存の固定は、採用列のCI paste-blockで有効化する。
  キット共通CIには特定OS・SDK・外部バイナリを前提としたジョブを置かない。

## 6. AGENTS.md / CLAUDE.md の規則（機械検査ではなく、読んで守る規則）✅ — v2.10 で多エージェント対応に再構成

上記1〜5が機械的に検査するのに対し、こちらは「読んで理解して守る」規則。
正本は各ファイルそのもの——ここでは何がどこに書いてあるか、そしてどの機械検査が
それを裏打ちするか（🚧含む）だけを示す。

**二分構成（v2.10・Phase 22——複製ではなく分割）**:
- **ルート `AGENTS.md` ＝ 規約の正本**（旧ルート CLAUDE.md の全章 §0〜§13 を移設）。
  Codex / Cline / Cursor / Windsurf 等はこれをネイティブに直読みする（AGENTS.md 標準）。
- **ルート `CLAUDE.md` ＝ Claude Code 固有の薄い層**。冒頭の `@AGENTS.md` インポート
  （Claude Code は AGENTS.md を直読みしないため、公式ドキュメント記載の到達経路が
  これ。symlink 方式は Windows でプレーンテキスト化するため不採用——§7.2 の前提）＋
  Claude Code 固有のフック層（§1・§2・§2b・§2c）の説明のみ。
- 同じ内容が2ファイルに存在しないため**同期が不要**（ドリフトが構造的に発生しない — G5）。
  インポート行の存在は `agents-import-missing`（hard — §3.3）が機械強制する。
- **可搬性の空白は残るフック層だけ**: §3〜§5 の門（pre-commit / commit-msg / pre-push / CI）は
  git フックと CI なので元よりエージェント非依存。Claude CodeとCodexは §1/§2/§2b/§2c の
  即時ゲートを持ち、その他のエージェントでは AGENTS.md §10-4 の心得と CI が同じ規則を守る。

### ルート `AGENTS.md`（旧ルート CLAUDE.md の章 — v2.10 で移設・章番号は不変）
| 節 | 内容 | 対応する機械検査 |
|---|---|---|
| §0 | よく使うコマンド＝ランタイム共通動詞の表（`dev.py` 10動詞） | §12.1（未配線は明示エラー） |
| §1-3 | ファイル500行・フォルダ7ファイル・ヘッダー一行の規約 | §3.3のsoft検査 |
| §4 | ドキュメントの置き場の分担（索引=STRUCTURE.md／設計根拠=plan.md／導入手順=README.md／技術選定理由=hoge.md／フォルダ知見=各フォルダCLAUDE.md／出戻り防止の地図=本書） | §3.2（STRUCTURE.md鮮度）・§3.4 検査5（feat⇔plan・hard — v2.8・G14） |
| §5 | フォルダ独立性・依存方向（3層構造は一方向のみ） | §3.3のhard検査 |
| §7 | ログ規則（秘匿・例外を握りつぶさない・出力基準） | §3.1 gitleaks・§3.3 log-direct-call / missing-catch-unwind（列充填）・§8 |
| §8 | テスト戦略（テストが通る状態でのみコミット・回帰テスト固定・flaky温床の禁止） | §3.3 test-sleep / test-nondeterminism / test-calls-solver-direct（列充填）・§3.4・§4・§5 |
| §10 | Git規則（GitHub Flow・コミットメッセージ規約） | §3.4（メッセージ形式） |
| §10-4 | **フックとの付き合い方**（迂回禁止・自動修正後は再実行するだけ・2回連続で落ちた時だけ原因調査） | §2・§3.1・§3.2 |
| §12 | 作業開始の定型手順（STRUCTURE.md→hoge.md→対象フォルダCLAUDE.mdの順で読む） | — |
| §13 | **発見の記録先**（再現できるバグ=回帰テスト／直感に反する箇所=近接コメント／フォルダ固有知見=フォルダCLAUDE.md——中央メモは作らない。近接コメントの制約がファイル外で噛んだらフォルダCLAUDE.mdへ**昇格**——v2.33） | §3.4（fix⇔テストの対で「回帰テスト固定」を強制） |

### ルート `CLAUDE.md`（Claude Code 固有の薄い層）
| 節 | 内容 | 対応する機械検査 |
|---|---|---|
| 冒頭 | `@AGENTS.md` インポート（規約本文への到達経路） | §3.3 `agents-import-missing`（hard） |
| フック層 | 編集直後 整形→lint（§1）・迂回/作業消失遮断＋probe（§2）・ターン終了ゲート（§2b）・所有権ガード（§2c）の挙動と一次対応 | §1 §2 §2b §2c そのもの |

### フォルダ別 `CLAUDE.md`（対象フォルダに触れた時だけ読まれる。エージェント非依存の運用は AGENTS.md §12 手順3「触るフォルダの CLAUDE.md を読む」が担う）
- 採用した各レイヤーの `CLAUDE.md` — その層だけに通用するテスト手順・デバッグ手順・
  「発見・ハマりどころ」。具体的な配置は表Bと採用列が正本。
- **書かれる契機**（v2.33）: 読む手順（§12 手順3）と記録先の分担（§13）だけでは1つも
  書かれないことがキット類似構成の導入先で実測された——規約が「読め」と言うファイルを
  「書く」トリガーがどこにも無く、知見はファイル内の近接コメントに散在したまま、別ファイルの
  テストを書く場面で同じ制約を踏み直す事故が実際に起きた（本節冒頭の外部裏書き②「CLAUDE.md
  の規則は影響であって強制ではない」の再現例）。契機を2つ明文化: ① AGENTS.md §13 の
  **昇格ルール**（近接コメントの制約がファイル外で噛んだ時） ② `dir-too-crowded` 警告に
  従うサブフォルダ分割時（警告文が CLAUDE.md 新設の検討を促す — §3.3）。全フォルダへの
  必須化は不採用——空のボイラープレートを量産して §12 手順3 の読む価値を薄める
  （偽陽性>価値 — §7.4 と同じ整理。soft 検査対象は従来どおり列の `REQUIRED_SOFT_PATHS` のみ）

## 7. `scripts/*.py` の仕様（契約）✅

対象: `scripts/generate_structure.py`（STRUCTURE.md を書いてよい唯一の主体）・
`scripts/check_structure.py`・両者が共有する走査モジュール・`scripts/dev.py`
（動詞ルーター——動詞の意味論は §12.1 が契約、実行環境の規律は本節に従う）。
本節は**契約**を規定する。
実装の細部はスクリプト本体の先頭ヘッダーコメントが正本。食い違ったら同一コミットで両方を揃える。

> **なぜ Python か**: 旧 bash 版は「ファイル毎に外部プロセスを起動」する構造で、
> Windows（Git Bash / MSYS2）のプロセス生成は1回数十msと極端に遅く、数百ファイル×
> 数チェックで数十秒かかっていた。Python は pre-commit 自体の実行環境なので実質追加依存
> ゼロで、単一プロセス・全ファイル1回読みなら同じ検査が1秒前後になる。あわせて
> CRLF・BSD/GNU差・cp932 という「bash on Windows」特有の罠も消える——ただし Python には
> Python の Windows 罠があるので §7.2 を絶対規則とし、インタプリタ解決の非決定性という
> 罠は **uv への一本化（§7.1）**で最初から塞ぐ。

### 7.1 言語と実行環境 — Python は必ず uv 経由
- **言語は Python、下限は 3.10**。実際に使う版はルートの **`.python-version` が正本**
  （Phase 1 で新設。uv がこのファイルに従い、該当版を自動取得・追従する）。
- **実行方法は `uv run scripts/xxx.py` のみ**。素の `python` / `python3` / `py` の直呼び、
  `pip` の直叩き、手動 venv は、**pre-commit の entry・CI・ドキュメントのコマンド例を
  含めて全面禁止**。理由: ① インタプリタ解決が決定的になる（PATH 汚染・ランチャー差・
  「手元では動く」の根絶）② Python 未導入マシンでも uv が自動で用意する（セットアップ
  手順が1つ減る）③ 依存が生えても扱いが変わらない（次項）。
- **標準ライブラリのみ**（`re` / `subprocess` / `pathlib` / `sys` / `argparse` / `difflib` /
  `tempfile` / `os`）を原則とする（§7.7 の性能予算のため）。依存がどうしても必要に
  なったら、**そのスクリプトの PEP 723 インラインメタデータ（`# /// script` ブロック）で
  宣言**して `uv run` に解決させる——`requirements.txt`・共有 venv は作らない
  （スクリプトが自己完結し、環境構築という工程自体を持たない）。
- Python 系ツールの導入は `uv tool install`（常用ツール。例: pre-commit）または
  `uvx`（単発実行）。
- 各スクリプト先頭のヘッダーコメントに「役割一行＋本節への参照」を書く
  （ルート `AGENTS.md` §1-3 のヘッダー規約は Python にも適用: `# xxx.py — 役割`）。

### 7.2 Windows 前提の絶対規則（1箇所の違反で恒常的な偽陽性・文字化けを生む）
- **すべての `open()` に `encoding="utf-8"` を明示**。Windows の既定エンコーディングは
  cp932 であり、付け忘れ1箇所で UnicodeDecodeError か文字化けになる。
  読み込みはさらに `errors="replace"`（検査対象に非UTF-8断片が混ざってもクラッシュしない）。
- **`STRUCTURE.md` の書き込みは `newline="\n"` を明示**。既定のままだと Windows で
  CRLF になり、CI（Linux）との間で恒常的に差分が出て鮮度チェックが偽陽性化する。
- **ファイル列挙は `git ls-files -z` を subprocess で呼び、NUL で分割する**。
  パスは常に `/` 区切りで返り、追跡済みファイルのみ・順序も安定。
  `os.walk` / `glob` は禁止（未追跡ファイルの混入・順序不定・セパレータ差）。
- **冒頭で `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`（stderr も同様）**。
  cp932 コンソールへ日本語メッセージを print すると UnicodeEncodeError で
  「検査自体のクラッシュ＝exit 1 誤爆」が起きるのを防ぐ。
- ソートは素の `sorted()`（Unicode コードポイント順）。locale 依存の照合を使わない。

### 7.3 共通走査モジュール（両スクリプトの土台）
- ファイル列挙・読み込み・シンボル/import 抽出の関数は**1つの共通モジュール**
  （例: `scripts/repo_scan.py`）に置き、両スクリプトはそれを import する。
  **同じ正規表現を2箇所に書くことを禁止**——二重実装は必ずドリフトする。
- **全ファイルはプロセス内で1回だけ読む**。ファイル毎の subprocess 起動は禁止。
- **O(N²) の禁止**: 孤立ファイル検出は「各ファイルについて全ツリーを検索」ではなく、
  1パスで（宣言されたモジュール集合, import された参照集合）を作り、集合演算で出す。
  旧 bash 版が数十秒かかった主因のひとつ。

### 7.4 `generate_structure.py` の契約
- **カレントディレクトリ非依存**: 冒頭で `git rev-parse --show-toplevel` によりルートを
  解決し、以降のパスはすべてルート基準。
- **引数なし（既定）**: ルートの `STRUCTURE.md` を再生成して上書き。生成に成功すれば
  **差分の有無に関わらず exit 0**——「古かったこと」の検知は §7.6 の pre-commit 機構に委ねる。
- **`--check`**: 書き込まない。最新なら exit 0、古ければ unified diff（`difflib`）を
  stderr に出して **exit 1**。
- **exit 2**: 内部エラー（git 不在・ルート解決失敗など）。
- **書き込みは原子的**: 同一ディレクトリの一時ファイル（`tempfile`）に全出力してから
  `os.replace()` で置換（Windows でも上書き置換が原子的に効く）。途中で中断されても
  壊れた `STRUCTURE.md` を残さない。
- **決定性（同一ツリー ⇒ バイト一致）**: 出力にタイムスタンプ・絶対パス・ホスト名・
  ユーザー名・実行環境情報を**含めない**（1つでも入れると鮮度チェックが恒常偽陽性化）。
  §7.2 の newline / encoding / sorted 規則と合わせて、**2回連続実行で差分ゼロ**が保証。
- **走査対象と公開シンボル抽出**: ツリー表示はgit追跡下のファイルのみ。生成物の除外と
  言語別シンボル抽出は `GENERATED_PATTERNS` / `SYMBOL_EXTRACTORS` の正本に従い、採用列で
  有効化する。どの抽出器も行指向の近似であり、完全なパーサを持ち込まない。
- **役割一行ヘッダー**: 各ファイル先頭のコメント1行（形式の正本はルート `AGENTS.md` §1-3）
  を抽出しパスの横に併記。未記述なら空欄のまま載せる（黙って落とさない。気づかせる役は
  §3.3 の soft 警告が担当）。
- **出力の骨格**: 先頭に必ず自動生成バナー
  `<!-- AUTOGENERATED by scripts/generate_structure.py — 手で編集しない。更新: uv run scripts/generate_structure.py -->`。
  以降、トップレベルディレクトリごとの節 → 「パス＋役割一行」のツリー →
  ファイルごとの公開シンボル一覧。体裁の細部はスクリプトが正本。

### 7.5 `check_structure.py` の契約
- 呼び出し・ルート解決・exit 2（内部エラー）は §7.4 と同一。
- **hard 違反が1つでもあれば exit 1、soft のみなら stderr 警告＋ exit 0**。
- 出力形式は §3.3 の契約どおり「1違反1行・先頭に規則ID・パス:行番号・説明」。
  検査項目の一覧（何を検査するか）は §3.3 が契約、検出パターンの実体はスクリプトが正本。

### 7.6 pre-commit 側のフック定義との対応
本書の Python スクリプトを呼ぶフックはすべて `language: system`・
`entry: uv run scripts/xxx.py` で定義する（§3.4 の `check_commit_msg.py` も同様）。
- **トップレベルに `default_stages: [pre-commit]` を必ず置く**。pre-commit の仕様では
  stages 未指定のフックは「インストール済みの全フック種」で走るため、無指定だと
  衛生〜構造検査が**コミット毎に2回**（pre-commit 段＋commit-msg 段）・push でさらに1回
  走る（実測でコミット毎2回→1回に半減。§7.7 の予算と G11）。commit-msg / pre-push で
  動かすフックは各フックの `stages` 明示が正本。
- `generate-structure`・`check-structure`: `pass_filenames: false`・`always_run: true`。
- `check-commit-msg`: `stages: [commit-msg]`。**`pass_filenames` は既定（true）のまま**
  ——commit-msg ステージはメッセージファイルのパスを引数として渡す仕様のため、
  false にすると引数が消えて壊れる。
**「差分があれば1回だけ失敗する」挙動の正体**は、pre-commit が「フック実行によって
ファイルが変更された」こと自体を失敗として扱う機構（§3.1 の自動修正フックと同じ仕組み）。
`generate_structure.py` 自身は exit 0 で構わない（§7.4）。

### 7.7 性能予算
コミット毎に走るため、**Windows 実機のフルスキャンで2秒以内（目標1秒）**。
計測は pre-commit を介さず `uv run scripts/check_structure.py` を直接 time で測る
（環境構築済みなら `uv run` 自体のオーバーヘッドは数十ms程度で予算内）。
**編集直後フック（§1・v2.5）は整形＋lint 合計で編集1回あたり3秒以内**——編集は
コミットより桁違いに高頻度のため、予算に収まらない言語の lint は編集直後に置かず
「該当なし（push 段で回収）」としてカタログに記録する（実測: `uvx ruff check` 単一
ファイルで約60ms）。guard コーパス再生は**当初「全行2秒以内」としていたが、v2.22で
Windows 32コア機の実測に基づき是正**: 並列度は `os.cpu_count()` から自動導出しつつ
上限を32→12へ下げ（実測: 8並列を境に頭打ち・旧上限32では逆に悪化するケースも
確認——標準ライブラリで Windows 含め動くため、ユーザー入力も調査スクリプトも不要）、
`.claude/hooks/guard_git_bypass.sh` 側の `grep`/`sed`/`tr` 直呼びを bash 組み込みの
`[[ =~ ]]`・パターン展開へ置き換えて子プロセス起動を1回あたり約18個→約2個
（jq・sed のみ残置）に削減した。**それでも実測は全74行で5〜8秒**（旧: 8〜9秒）——
プロセス起動自体のOSコストが支配的で、2秒という当初予算は複数コアでも達成できない
という実測に基づき、予算を「全行10秒以内（目標5秒）」へ是正する（行数増で超過したら
並列度→guard 内のプロセス起動回数の順に削る。計測は実機・複数コア前提。1コアの
サンドボックス実測は予算対象外）。
予算超過の第一容疑者は常に「プロセス起動回数」と「O(N²)」（§7.3）——今回の是正自体が
その実例（guard 1回の呼び出しで `jq`/`tr`/`sed`/`grep` が10〜15回起動していたことが
根本原因で、並列度の調整だけでは効かなかった）。

## 8. ログ規則の機械化（検査器は同梱✅——lint昇格と単一出口の実装・有効化は §11 Step 6〜7）

ルート `AGENTS.md` §7 は現状すべて「読んで守る」規則。以下でその大半を機械検査に変換する。
機械化できない残り（識別子は載せる／中身は載せない、の判断）は引き続き規約側の責務であり、
その境界を本節で明示する。

### 8.1 リンタ昇格（Phase 2）— 「うっかり print デバッグ残し」を型エラーと同格にする
- **設定値の正本は採用列の「lint昇格」行**（`bindings/catalog.md`）。対象言語のprint系直呼び・
  空catch等をerrorへ昇格するかは、言語ごとの公式lint設定で定義する。
- 例外は**その場に `#[allow(...)]` / `// ignore:` を明示**して初めて許される
  （例外が目に見える形でしか存在できないようにする）。
- 発火点は採用列が配線するpre-pushとCI。

### 8.2 出口の単一化（Phase 4）— フォーマット規約を「規約」から「1箇所の実装」に変える
`[タグ] 操作名: 詳細 (+Xms)` という形式は grep では検証できない。そこで出口を1つにする:
- 各採用列はログ出口の実装ファイルと公開APIを1つ定義する。print系を呼んでよいのはその
  出口だけであり、他ファイルの直呼びは §3.3 の `HARD:log-direct-call` が止める。
- FFI等の境界がある列は、必要な例外・panic境界を `FFI_BOUNDARY_FILE_PATTERNS` と
  `CATCH_UNWIND_PATTERN` で定義する。存在検査はtrip-wireであり、正しい回復処理はレビューの責務。
- **出力の中身（v2.20 — サンプル実装）**: `[タグ] 操作名: 詳細 (+Xms)` は人間が読む前提の
  概念的な形（このキットが規定するのはここまで——ログレベルの種類・タイムスタンプ・
  構造化するか・出力先はプロジェクトの判断 — §8.4）。python-uv 列（`bindings/catalog.md`）
  には、この形を実際に満たす**動作確認済みの参考実装**を追加した——独自スキーマを発明
  せず OpenTelemetry Logs Data Model の命名・構造化ログの実務コンセンサス（ISO 8601 UTC
  timestamp・level・trace_id）・12-factor app「ログはイベントストリーム」に揃えた1行1JSON。
  サンプルは**貼り替え自由な出発点**であり、`check_structure.py` は中身を検査しない
  （`log-direct-call` が見るのは「経由したか」だけ）。他列（ts-react-web/rust/dart-flutter）
  へも同型のサンプルを展開済み（v2.40——各列とも実行して有効なJSON出力を4ケース確認。
  `LOG_BOUNDARY_PATTERNS`/`LOG_CALL_PATTERN` は ts-react-web が充填済み（@12・v2.48——
  被覆検査4ケースDoD実測済み）、rust / dart-flutter は未実施のまま——§8.4 の
  被覆検査DoDを伴う列充填の仕事として残る）。
- **出口の契約テスト（v2.48 — Phase 50・§9.7 の第2層をログ出口へ適用）**: 貼ったサンプルは
  ドキュメント側だけ直すと腐る。採用先は出口の**形式を固定するテスト**（1行1JSON・
  必須フィールド・error 時の level 昇格——実行可能サンプルは ts-react-web 列 @12）を同梱し、
  CI が緑である限り**出口の実物が形式の正本**であり続けるようにする（G5——§11 Step 7）。
  `check_structure.py` が中身を検査しない原則は不変——形式を守るのは検査器ではなく、
  プロジェクト自身のテストの持ち場。

### 8.3 秘密の多層防御と責務の境界
- コミット面 = gitleaks（§3.1）が機械検査。
- ログ面 = 出口が `logOp` に単一化されるため、「トークン・パスワード・APIキーを
  `logOp` に渡さない」という判断1点に絞られる。これは機械化しない（できない）ことを
  明示する——ここが規約（ルート `AGENTS.md` §7）に残る最後の責務。

### 8.4 ログ被覆の機械化と限界（`missing-log-coverage` — v2.19・Phase 31）

- **「重要度」は機械化できない**: どの関数がログに値するかは業務文脈の理解を要する
  意味判断であり、構文パターンしか見られない静的検査には原理的に不可能。全関数への
  ログ強制は①ノイズで信号対雑音比を悪化させる②`logOp("x","called","")` のような
  空呼びで簡単に骨抜きにできる、の2点で不採用（実測: Microsoft Research の産業調査
  ではログ済み関数は全体の一部に留まる——logOp呼び出しの有無だけを見る素朴な網羅性は
  現実の実務とも整合しない）。
- **採った設計**: 対象を「重要度」でなく**客観的に検出できる境界**（I/O・外部呼び出し・
  エラーハンドラ——`LOG_BOUNDARY_PATTERNS`）に絞り、境界の前後 `LOG_BOUNDARY_WINDOW`
  行以内に `logOp` 呼び出しか `NO-LOG: 理由` コメントのどちらかを要求する（soft）。
  これは新規発明ではなく、ESLint `eslint-comments/require-description`・Rust clippy
  `allow_attributes_without_reason`・SonarQube S108/S2486（空catchはコメントで許容）
  ・Honeycomb の DBマイグレーションlinter（`atlas:nolint` 注釈）が実際に採用している
  「**存在検査＋可視化**」の定石を踏襲したもの。
- **機械化の限界はここまで**: `NO-LOG:` の**理由の妥当性**は検証しない（できない）。
  空虚な理由でも門は通る——RED-FIRST-EXEMPT と全く同じ境界。ここから先は
  §10 実行規律のレビュー責務（EXEMPT乱用監視と同型の定期監査）に委ねる。Honeycomb も
  同じ設計で「人を信頼し、後で気づいて直す」と公言している——見える化で十分という
  判断はこのキット固有の妥協ではなく、現場で実証済みの落とし所。
- ランタイムでの重複ログの間引き（Sentryのフィンガープリンティング・zapのsampling等）
  は別レイヤーの話であり、ソースコードの被覆検査とは独立——このキットの対象外
  （列採用時にロギングライブラリ側の機能として個別導入する）。
- テスト実行時の出力量に応じて**ログの有無や配置をソースコード側で自動変更する**
  仕組みは不採用: ①出力量は重要度と相関しない（ホットパスほど出力が多く、閾値で
  自動オフにすると一番見たい場所から消える）②テスト実行の偶発的な特性（カバレッジ・
  実行順）に依存し G1 決定性と衝突する③レビューを経ずにソースの挙動が変わる——
  `SURVEY_ZERO_REVIEW.md` が却下した「自己治癒ランタイム」と同じ「門の外の変更経路」。

## 9. テスト規則の機械化（fix⇔テスト対は同梱✅——非決定検査は列充填・ラッパーは §11 Step 8）

ルート `AGENTS.md` §8 の「flaky 温床の禁止」「回帰テスト固定」を機械検査に変換する。
このプロジェクトは**確率的ソルバー（進化計算＋CP-SAT）を抱える**ため、一般則に加えて
ソルバー固有の決定性対策が本命。

### 9.1 `solve_for_test` ラッパー（Phase 5）
- engine に `pub fn solve_for_test(input, seed: u64, max_time: Duration) -> …` を用意する。
  中身は本体 solve の薄いラッパーで、**必ず** `random_seed = seed`・
  `num_search_workers = 1`・`max_time` を設定して呼ぶ。
- 根拠: CP-SAT は並列探索（複数ワーカー）とシード未固定で実行毎に結果が揺れる——
  単ワーカー＋シード固定が flaky 根絶の必要条件。`max_time` は `cargo test` に組み込み
  タイムアウトが無いことへのハング保険（無限に待つ CI ＝最悪の出戻り）。
- テストコードからの本体 solve 直呼びは §3.3 の `HARD:test-calls-solver-direct` が止める。
- 完成条件に含める性質: **同じ seed で2回実行して同じ結果**（決定性のセルフテスト）。
- **UNKNOWN は第三のラベル**（v2.41・Phase 43）: `max_time` 打ち切りの結果は成功/失敗の
  二値でなく**充足/違反/判定不能（UNKNOWN）の三値**で数える。過制約帯（相転移帯）では
  打ち切りが一定数出るのが正常であり、UNKNOWN を黙って捨てる集計は「難しい問題ほど
  欠測する」選択バイアスを乗せる——G9 沈黙の禁止のテスト版。バッチ検証・性質テスト
  （§9.6）では UNKNOWN 件数を必ず表示し、比率の常態的な上昇は `max_time` か定式化の
  見直しトリガーとして扱う（表示のみ——閾値判定の自動化はしない。§3.6 と同じ整理）。

### 9.2 非決定入力の禁止パターン（Phase 5）
テストファイル内に限り、**採用列の「テスト内 非決定」パターン**を §3.3 の
`HARD:test-nondeterminism` として検出する（移植元の例——Dart: `DateTime.now()`・引数なし
`Random()`／Rust: `thread_rng`・`SystemTime::now`）。
時刻や乱数が必要なテストは固定値を注入する（seed 付き `Random(42)`、時刻は引数/
Clock 抽象で渡す）。既存の `test-sleep` 検査と同じ機構にパターンを足すだけ（§7.5）。

### 9.3 fix ⇔ 回帰テストの対 ✅
契約は §3.4 の検査2。ルート `AGENTS.md` §13「再現できるバグ → 回帰テスト」を、
善意ではなく commit-msg フックで担保する。同梱テストが**親コミットで赤だった**
（＝バグを再現していた）ことの機械証明は CI の `red-first` ジョブ（§5 — v2.7）。

### 9.4 E2E とカバレッジ
CI 側の契約として §5 に記載（integration-test-windows ジョブ／カバレッジは表示のみ→
ラチェット）。

### 9.5 外部I/Oの検疫（test-network）— 時刻・乱数に続く第3の非決定源
- 外部I/O（HTTP・生ソケット・外部LLM API・決済・メール送信）は、**単一のシーム**
  （採用列の「外部I/Oシーム」の置き場所）の向こうへ隔離する。UI・ドメイン層に直呼びを
  書かない——§8.2「出口の単一化」と同型の発想を入口にも適用する（G6・G8）。
- **テストが使ってよいのは記録済みフィクスチャ / フェイクのみ**。テストファイル内の
  直呼びは §3.3 の `HARD:test-network` が止める（パターンは採用列）。ネットワークに出る
  テストは flaky（G1違反）と秘匿漏れ（§8.3）の両方の温床。
- 本物のI/Oを検証する統合テストが必要な場合は、E2E（§12.4）か CI の専用ジョブへ隔離し、
  例外は目に見える形でのみ許す（§8.1 と同じ思想）。
- **非決定性の再現そのものがテストの本質という正当なケース**（実ブラウザの分割TCP
  書き込みタイミングを再現する回帰テスト等）が存在する（v2.25・Phase 35）。この場合は
  `test-sleep`・`test-nondeterminism`・`test-network` の3規則いずれも、該当行の前後
  `NONDETERMINISM_EXEMPT_WINDOW`（既定3）行以内に `NONDETERMINISM-EXEMPT: 理由`
  コメントがあれば免除する。理由の妥当性は検証しない——存在検査のみ（`NO-LOG:` /
  `RED-FIRST-EXEMPT:` と同じ「見えるようにするだけ」の境界 — G9）。乱用監視はレビューの
  責務（§8.4 の `NO-LOG:` と同じ運用）。

### 9.6 オラクルの種類——実例より性質、性質より差分（v2.41・Phase 43）

LLM が生成したテストは、期待値の導出が実装と同じ思考で行われると**実装と欠陥を共有**する
（self-deception サイクル——外部調査の判定ごと `surveys/SURVEY_LLM_TESTGEN.md` が正本）。
fix⇔テスト対（§9.3）と red-first（§5）は「テストが存在し、バグを再現した」ことまでを
機械化したが、**オラクルの種類**（テストが何と突き合わせて正誤を判定するか）は本節までは
無規定だった。確率的コンポーネント有（表B）のリポジトリでは、検証の書き方を次の優先順に
する:

1. **差分検証（独立オラクルがある場合——表B「独立オラクルの有無」）**: 検証関数と
   ソルバー本体は「制約充足」という同じ問いに対する**2つの独立な実装**。両者の不一致は
   どちらかのバグ（食い違い＝機械検出可能な赤）。独立チェッカーは1関数に集約し、全性質
   テストから呼ぶ。CI ジョブ化は列充填。
2. **性質形（独立オラクルが無い場合の上限）**: 期待値を書かず、どんな出力でも成り立つ
   べき**不変量**（例:「どのビンも容量を超えない」）と**メタモルフィック関係**
   （例:「入力を増やして結果集合が縮むことはない」）だけを主張する。PBT ライブラリ
   （hypothesis / proptest 等——列の「性質テストマーカー」）が入力生成を担う。
   実行可能なサンプルは python-uv 列 @8（違反注入で fail まで実測済み）。
3. **実例オラクル（期待値のハードコード）**: 境界ケースの固定・red-first の回帰再現に
   限る。実例**だけ**で確率的コンポーネントを検証しない。

- **機械検査**: `SOFT:missing-property-test`（§3.3）——`SOLVER_DIRECT_CALL_PATTERNS`
  充填（=表Bで確率的コンポーネント有）なのに、テストのどこにも性質形テストの痕跡
  （`PROPERTY_TEST_MARKERS`）が無い。**存在検査のみ**——性質の中身・質は機械で測れない
  （`NO-LOG:` と同じ境界 — G9）。空虚な性質（`assert result is not None`）でも門は通る
  ——質の監視はレビューと、保留の変異テスト（§10——性質が mutant を赤にできるか）の持ち場。
  soft の理由: 偽陽性率が未知（v2.34 非対称閾値②）。
- **買うもの/買わないもの（§2e と同じ型の脅威モデル）**: 差分検証が検出できるのは
  「検証関数とソルバーの**どちらか一方だけ**が間違っているケース」まで。**共通の定式化
  ミス**（仕様の読み違えが両実装へ同じ形で入る——「未満」を「以下」と両方で書く等）は
  原理的に検出不能で、両者が仲良く緑になる。この層の検査機械は存在しない——仕様との
  突き合わせは人間レビューとユーザーフィードバックの持ち場。ソフト制約の重み・
  「出力の自然さ」も同様に対象外（正解が定義されないため性質が書けない——UI 第二層
  （§10 保留）と同じ理由で門の射程外）。
- 一般リポジトリ（確率的コンポーネント無し）へ性質検査を**強制しない**判断も記録する:
  強い不変量が書けるのは構造化された領域だけで、CRUD/UI に強制すると空虚な性質で
  骨抜きになる（§8.4 が全関数ログ強制を退けたのと同じ判定——SURVEY_LLM_TESTGEN.md §3）。

### 9.7 実行される参照実装（雛形）——「サンプルは示すが強制しない」の構造（v2.48・Phase 50）

「規定のやり方でテストとログを書いてほしいが、機械強制はできない」（重要度・書き方の判断は
文脈依存——§8.4 と §9.6 が繰り返し到達した結論）という課題への答えを、3層のレールとして
明文化する。**hard 検査は増やさない**:

1. **第1層——レール＝コードの形で与える**: 規則を文章にせず実装を先に置く（ログ単一出口
   §8.2・注入シーム §9.2/§9.5/§12.2・テストヘルパー）。従う側は「規約を守る」のではなく
   「用意された部品を使う」だけになる——従わない方が難しい状態が最強のレール。
2. **第2層——サンプル＝実行される参照実装**: ドキュメント内のサンプルは書いた瞬間から腐る。
   CI が常に実行する本物のコードとして置けば、緑である限りコピー元として古くならない。
   採用先は、**注入シーム（フェイクAPI・Clock）・固定時計・testid・境界のログ記録までを
   1機能で実演する参照実装＋テストを1つ**置き（§11 Step 8b）、ログ出口には形式を固定する
   **契約テスト**を同梱する（§8.2・Step 7）。AGENTS/CLAUDE.md からは「新機能はこれを
   雛形にする」と**参照するだけ**にする——規則の羅列を書かない（G3・G5）。
3. **第3層——検査＝最小限の hard＋理由付き免除の soft（既存・変更なし）**: hard は正当な
   例外が原理的に存在しないもの（`log-direct-call`・`test-network` 等）だけ。境界被覆は
   soft＋`NO-LOG: 理由`（§8.4）、非決定は `NONDETERMINISM-EXEMPT: 理由`（§9.5）——逸脱を
   禁止せず、**目に見える形でしか存在できなくする**。

- 参照実装の**中身は機械検査しない**（サンプル貼り替え自由の原則 §8.2 と同じ境界）。
  雛形が実演すべき要素の存在は、既存の門（`test-nondeterminism`・`test-network`・
  `ui-missing-testid`・`missing-log-coverage`）が participant として自然に検査する——
  参照実装専用の新しい規則は作らない（G11——検査の重複は予算を食う）。
- 実行可能な具体物: ログ出口の契約テスト＝ts-react-web 列 @12 paste-block。
  性質形テストのサンプル＝python-uv 列 @8（§9.6）。参照実装1機能の paste-block は
  列ごとにアプリの形が違うため置かない——Step 8b の完了条件（E2E 1本と同時に立てる）を
  正本とする（判断ごと記録）。

## 10. 実装ロードマップ（🚧 の唯一の正本）

### 実行規律（§10 の Phase と §11 の Step に共通・LLM のサボりを塞ぐ）

LLM の実装セッションは、省略・先送り・自己申告完了に流れやすい。以下は「心得」ではなく
**判定規則**——1つでも破れば、その Phase / Step は完了扱いにならない。

1. **順序固定・スキップ禁止**。番号順に1つずつ。後続の作業は前段で立てたゲートに
   守られる前提で並んでいるため、順序を入れ替えると「検査されない作業区間」が生まれる。
   （§11 の Step は機械化: `bootstrap-order` が台帳の順序を強制 — §3.5・v2.12）
2. **1 Phase（1 Step）= 1 ブランチ = 1 PR**。複数をまとめない——どのゲートがどの変更を
   検証したのか、後から追えなくなる。
   （§11 の Step は機械化: `bootstrap-multi-flip` が ✅ 化を1コミット1Stepに制限 — §3.5）
3. **完了＝実行結果であり、自己申告ではない**。DoD にあるコマンドを実際に実行し、
   **成功系と違反注入の失敗系の両方**の出力を確認してから ✅ にする。「実装した」は
   完了ではない。「わざと違反して落ちるのを見た」が完了（冒頭の原則）。
   （§11 の Step は機械化: ✅ の主張は `check-bootstrap` が検証可能なアサーションを
   その場で再実行して検証する — §3.5。監査器が再現できない DoD 部分は本規律が心得として残る）
4. **✅ 化は実装と同一コミット**。実装より先に付ける・後から別コミットでまとめて付ける、
   はどちらも禁止（虚偽 ✅ の典型）。後続セッションへの監査ルール: **✅ なのに違反注入で
   落ちない項目を見つけたら、🚧 に戻して再実装する**。
   （§11 の Step は機械化: `bootstrap-false-done` がこの監査ルールそのもの——✅ 化コミット
   自体が検証に合格しないと積めず、✅→🚧 の差し戻しが正規経路 — §3.5・v2.12）
5. **placeholder・TODO・空関数・コメントアウトされた検査の禁止**。スタブを置いた時点で
   未完了。`TODO` の残置は監査 Step の grep で機械的に検出される（§11 Step 10）。
6. **省略記法での完了扱いの禁止**。「他言語も同様」「残りの規則も同じ要領で」で
   まとめない。バインディング表の全行・規則IDの全行を、**1つずつ実装し1つずつ違反注入**する。
   （v2.45——「1つずつ違反注入」の実体はコーパス対象なら `dev.py dod` の1ケース。
   ランナーの PASS 一覧がそのまま実績であり、手動注入が要るのは対象外5分類
   （Phase 47 追記）に該当する有効化規則だけ。**dod で済む注入を手でやり直さない**——
   逆向きの二度手間もサボりの一形態）
8. **違反注入の後始末に `git checkout` / `git restore` を使わない**。未コミットの実装ごと
   巻き戻す（v2.45 のキット開発中に実測——注入テストの後始末で書きかけの検査器を消した）。
   正規経路はコーパス（`dod` / `selftest`——後片付けは機械）。手動注入が要る時は
   **注入の前にコミット**し、除去は注入ファイルの削除・編集の逆適用で行う。
7. **途中でターンを終えない**。「続けますか?」で手を止めるのはサボりの一形態。
   終えてよいのは (a) その Phase / Step の DoD をすべて満たした時、または
   (b) 本当に手が止まるブロッカー（DoD が物理的に実行不能等）を具体的に報告する時のみ。
   必要な決定は着手前（§11 なら Step 0、§10 なら契約節の読解）で確定させ、
   途中で仮定して進めない・確定済みの事項を再確認して止まらない。
   （機械化: §2b の Stop ゲートが (a)(b) 以外の終了を差し戻す — v2.4。ただし
   Claude Code 外の環境では本規律が引き続き心得として効くため、文言は残置する）

### 実装セッションの回し方
1. 状態表で未完了 Phase の**先頭**を選ぶ（飛ばさない——後続 Phase は Phase 1 の
   Python 基盤に検査を足す構造になっている）。
2. その Phase の「契約」列の節を読む。実装対象の既存ファイルがあればそれも読む。
3. 実装する。
4. **DoD をすべて満たす**（違反注入含む。上の実行規律 3）。
5. 「同一コミットで更新する文書」欄を処理し、本書の該当箇所を 🚧 → ✅ に更新する。

### 状態表

| Phase | 機構 | 契約 | 状態 |
|---|---|---|---|
| — | 整形フック／迂回防止／衛生チェック／gitleaks／pre-pushフック枠／CI checks ジョブ／STRUCTURE.md鮮度・構造検査（Python/uv版） | §1 §2 §3.1 §3.2 §3.3 §4 §5 | ✅ |
| 1 | 構造スクリプトの Python(uv) 移植（高速化） | §7 | ✅（v2キット同梱） |
| 2 | lint昇格・analyze/clippy前倒し・ツールチェーン固定 | §8.1 §4 §5 | 🚧 |
| 3 | commit-msg 検査（形式＋fix⇔テスト） | §3.4 §9.3 | ✅（v2キット同梱） |
| 4 | ログ出口の単一化＋対応 hard 検査 | §8.2 §3.3 | 🚧 |
| 5 | テスト決定性（solve_for_test＋非決定パターン） | §9.1 §9.2 §3.3 | 🚧 |
| 6 | ブリッジ鮮度＋生成物 deny 拡張 | §4 §2 | 🚧 |
| 7 | CI 拡張（integration_test on Windows・カバレッジ表示） | §5 | 🚧 |
| 8 | ランタイムレール（共通動詞・決定性供給・操作/観察・外部I/O検疫） | §12 §9.5 | 🚧 |
| 9 | guard 迂回コーパス（門番の回帰テスト） | §2 | ✅（v2.4 同梱） |
| 10 | probe 動詞（迂回防止への事前照会） | §2 §12.1 | ✅（v2.4 同梱） |
| 11 | ターン終了ゲート（Stop フック＝実行規律7の機械化） | §2b | ✅（v2.4 同梱） |
| 12 | 編集直後リント（PostToolUse 第2段・3秒予算） | §1 §7.7 | ✅（v2.5 同梱） |
| 13 | 依存追加の明示化 `undeclared-dependency`（commit-msg 検査4） | §3.4 | ✅（v2.5 同梱） |
| 14 | 作業消失ガード（非可逆な消失に限定した遮断＋コーパス前提列） | §2 | ✅（v2.5 同梱） |
| 15 | 世代交代 API 検査 `deprecated-api` | §3.3 | ✅（v2.6 同梱） |
| 16 | 所有権ガード（人間の未コミット変更の上書き防止） | §2c | ✅（v2.6 同梱） |
| 17 | feat⇔plan 対 `feat-without-plan`（soft 導入——v2.8 で hard 昇格 = Phase 19） | §3.4 | ✅（v2.6 同梱） |
| 18 | red-first 証明 CI（fix テストが親コミットで赤だった証明） | §5 | ✅（v2.7 同梱） |
| 19 | feat⇔plan 対の hard 昇格＋G14「意図の保存」新設（決定点①=案Aで確定） | §3.4・.guardrails/GOALS.md レンズ4 | ✅（v2.8 同梱） |
| 20 | Stop ゲート条件B（`dev.py check` 赤で差し戻し——決定点②=強化案で確定） | §2b | ✅（v2.9 同梱） |
| 21 | red-first の required 化＋EXEMPT 乱用監視（決定点③=確定） | §5・ルート AGENTS.md §8 | ✅（v2.9 同梱） |
| 22 | AGENTS.md 可搬化（規約の正本を全エージェント共通へ二分——保留のトリガー発動） | §6 | ✅（v2.10 同梱） |
| 23 | MCP 採用許可リスト `mcp-not-allowed`（2026-07-07 調査の判定を門に固定） | §3.3 §12.4・catalog 注記 | ✅（v2.11 同梱） |
| 24 | ブートストラップ監査 `check-bootstrap`（実行規律1〜4の機械化——虚偽✅の門） | §3.5・.guardrails/BOOTSTRAP.md | ✅（v2.12 同梱） |
| 25 | feat-without-test（soft 導入——著名キット調査②の採用1） | §3.4 検査6 | ✅（v2.13 同梱） |
| 26 | commit-too-large（soft 導入——著名キット調査②の採用2） | §3.4 検査7 | ✅（v2.13 同梱） |
| 27 | kit-source-exempt（キット原本自身の Stop ゲート永久赤の解消） | §3.3 | ✅（v2.14 同梱） |
| 28 | context-doc-too-large（soft——調査③の採用。Skills 化保留のセンサー） | §3.3 | ✅（v2.17 同梱） |
| 29 | env-file-tracked（hard——調査④の採用1。gitleaks の空白） | §3.3 | ✅（v2.18 同梱） |
| 30 | test-shrink（soft——調査④の採用2。既存テスト弱体化の可視化） | §3.4 検査8 | ✅（v2.18 同梱） |
| 31 | missing-log-coverage（soft——I/O・エラー境界のログ被覆＋NO-LOG可視化） | §8.4 | ✅（v2.19 同梱） |
| 43 | missing-property-test（soft——オラクル契約 §9.6 の存在検査）＋UNKNOWN三値＋表B独立オラクル＋降格の統治 | §9.6 §9.1 §11 Step 0・GOALS 運用 | ✅（v2.41 同梱） |
| 44 | 導入 CLI（--detect/--diff/--check）＋管理区画スプライス＋selftest/doctor/probe --live | §11 前段・§12.1・§2・Step 4 ⑩ | ✅（v2.42 同梱） |
| 45 | 門の台帳 GATE_REGISTRY＋`dev.py gates`＋gates-registry-drift（機能発見の導線） | §12.1・§3.3 | ✅（v2.43 同梱） |
| 46 | 導入経路の効率化（easy 廃止・existing/update の CLI 前提化） | PROMPT_claude_code_existing / _update | ✅（v2.44 同梱） |
| 47 | 充填と規則DoDの機械化（fill_bindings＋rule-dod コーパス＋機械/LLM 分担の明文化） | §11 前段・§11 分担節・catalog FILL マーカー | ✅（v2.45 同梱） |
| 48 | フックシム改変の迂回封鎖（.git/hooks/ の rm/mv/chmod/切り詰め＝pre-commit uninstall の非語版） | §2・tests/guard_corpus.tsv | ✅（v2.46 同梱） |
| 49 | Fable更新後監査の是正（Windows迂回・Codex fail-closed・全列DoD・YAML機械充填・充填原子性） | §2・§11・§12.7 | ✅（v2.47 同梱） |
| 50 | 実行される参照実装（3層レールの明文化＋ログ出口の契約テスト＋ts-react-web ログ境界充填） | §9.7 §8.2 §11 Step 7/8b・catalog ts-react-web@12 | ✅（v2.48 同梱） |

### Phase 1 — Python(uv) 移植 ✅（v2キットに同梱済み）
- `.python-version`・`scripts/repo_scan.py`・`generate_structure.py`・`check_structure.py`
  （§7 準拠）、pre-commit の `uv run` entry、`guardrails-ci.yml` の setup-uv——すべて同梱。
  移植先での DoD 実測（決定性2回一致・違反注入・2秒以内）は §11 Step 2 に統合されている。

### Phase 2 — 静的ゲート一括（すべて設定のみ・相互独立）
- 変える: `app/analysis_options.yaml`・`engine/Cargo.toml`（§8.1）、
  `.pre-commit-config.yaml`（analyze/clippy を pre-push へ §4）、
  `engine/rust-toolchain.toml` 新設・CI の Flutter 版固定・`build.rs` の
  `ORTOOLS_DIR` 検証（§5）。gitleaks はキット同梱済み（§3.1）。
- DoD: 違反注入——① `print` 残し・`dbg!`・空 catch がそれぞれ analyze/clippy で落ちる
  ② `ORTOOLS_DIR` を外して build.rs が明確なメッセージで落ちる。
  全違反を除去して CI グリーン。
- 文書: 本書の該当ステータス。

### Phase 3 — commit-msg 検査 ✅（v2キットに同梱済み）
- `scripts/check_commit_msg.py`・commit-msg ステージのフック定義・
  `default_install_hook_types` の `commit-msg`——すべて同梱。移植先での実体は
  **`pre-commit install` の実行**と DoD 実測（§11 Step 5 に統合）。

### Phase 4 — ログ出口の単一化
- 作る: `app/lib/services/log.dart`・`engine/src/logging.rs`（§8.2）。
- 変える: 既存の `debugPrint` 直呼びを `logOp` へ置換、`check_structure.py` に
  `log-direct-call`・`missing-catch-unwind` を追加（§3.3）。
- DoD: ① 適当なファイルに `debugPrint` を書くと hard で落ちる ② FFI 境界ファイルから
  `catch_unwind` を消すと落ちる ③ 置換後の実ログが `[タグ] 操作名: 詳細 (+Xms)` 形式で
  出ることを1本の統合テストか手動起動で確認。
- 文書: `app/CLAUDE.md`・`engine/CLAUDE.md` に使い方1行、本書。

### Phase 5 — テスト決定性
- 作る: `solve_for_test`（§9.1）。変える: 既存テストをラッパー経由に移行、
  `check_structure.py` に `test-calls-solver-direct`・`test-nondeterminism` 追加（§3.3 §9.2）。
- DoD: ① 同一 seed で2回実行し結果一致 ② テストからの solve 直呼び・`DateTime.now()`
  などの違反注入がそれぞれ落ちる ③ `max_time` を極端に短くしてもハングせず返る。
- 文書: `engine/CLAUDE.md`（ラッパーの使い方と根拠1〜2行）、本書。

### Phase 6 — ブリッジ鮮度
- 変える: `.pre-commit-config.yaml` に pre-push の codegen 鮮度フック（§4）、
  `.claude/settings.json` の deny に生成物パス追加（§2）。
- DoD: ① Rust 側の公開シグネチャを1つ変えて push すると落ち、codegen 実行＋コミットで
  通る ② 生成物への Edit が deny される。
- 文書: 本書。

### Phase 7 — CI 拡張
- 変える: `.github/workflows/guardrails-ci.yml` に `integration-test-windows` ジョブと
  カバレッジサマリ（§5）。
- DoD: ① PR で新ジョブが緑 ② integration_test を1本わざと壊した PR が赤になる
  （E2E ゲートの違反注入）③ OR-Tools キャッシュが2回目以降のジョブで効いている。
- 文書: `engine/CLAUDE.md`（OR-Tools の CI 上の取得・キャッシュ手順）、本書。

### Phase 8 — ランタイムレール（§12 の具体化。新規リポジトリでは §11 Step 8b が同内容）
- 作る/変える: `scripts/dev.py` の COMMANDS 充填（採用列）・時刻注入シーム（§12.2）・
  `.mcp.json`（操作レールが MCP の列）・`test-network` / `ui-missing-testid` の有効化・
  E2E CI ジョブ（§5）。
- DoD: ① 全動詞が「配線済み」か「該当なし」の判断込みでカタログに記録済み
  ② `reset` → 同一操作2回 → 状態一致（G1 の実測）③ エージェントが操作レール経由で
  UI を1回操作し、観察レールで結果（コンソール・DB）を読めたことの実測
  ④ `test-network`・`ui-missing-testid` の違反注入が赤 ⑤ E2E を1本壊した PR が赤。
- 文書: 本書 §12・AGENTS.md §0 の動詞表・カタログの「実測済み」昇格。

### Phase 9〜11 — v2.4 同梱 ✅（guard コーパス／probe／ターン終了ゲート）
- 契約と正本は §2（コーパス・probe）・§2b（Stop ゲート）。移植先での実体は DoD 実測
  （コーパス全行 PASS＋規則1つの無効化注入で赤／probe の DENY・ALLOW／Stop の
  5注入——特に**§2b は fail-open の実測**で、§2 と逆向きの注入を飛ばさない）。

### Phase 12〜14 — v2.5 同梱 ✅（編集直後リント／依存追加の明示化／作業消失ガード）
- 契約と正本は §1（整形→lint の直列2段）・§3.4 検査4・§2 作業消失ガード＋コーパス前提列
  （＋§7.7 の3秒/編集予算）。詳細仕様は各節へ集約済み——本 Phase 節は残置しない。
- 設計時に「実装時確定」としていた2点は次のとおり確定（残置なし）:
  ① **整形→lint の実行順**——公式仕様では同一 matcher の複数フックは並列・順序不定のため、
  2エントリ登録ではなく `settings.json` の**直列1コマンド**で配線（§1。短絡・exit 伝播は実測済み）。
  ② **dirty 条件付き規則の回帰再生**——手動 DoD ではなく**コーパスの前提列**（dirty/clean の
  一時リポジトリフィクスチャ — §2）で機械再生する。
- 移植先での実体は DoD 実測（lint 違反注入→exit 2＋stderr・3秒予算・ツール不在素通し／
  依存追加の4境界＝言及なし赤・言及あり緑・lockfile素通し・版更新素通し／dirty でブロック・
  clean で素通し・`rm -rf .git` 常時ブロック／コーパス全行 PASS＋規則1つの無効化注入で赤）。
- Phase 14 の旧 DoD ⑤（「人間の WIP・自分の WIP を消せない」対の §2c 文書確認）は
  **Phase 16 の DoD へ繰り越し**（下記 Phase 16 ⑤——片翼だけでは対にならないため）。

### Phase 15〜17 — v2.6 同梱 ✅（deprecated-api／所有権ガード／feat⇔plan 対）
- 契約と正本は §3.3 `deprecated-api`（BINDING は `repo_scan.py` の `DEPRECATED_PATTERNS`・
  出典規律はカタログ注記）・§2c（所有権ガード——`session_baseline.sh`＋`guard_human_wip.py`・
  fail-open の非対称・作業消失ガードとの対の完成＝Phase 14 からの繰り越し分）・
  §3.4 検査5 `feat-without-plan`（soft・表示のみ。BINDING は `PLAN_LAYER_ROOTS` /
  `PLAN_DOC_PATTERNS`——空なら不発＝列充填で有効化）。詳細仕様は各節へ集約済み。
- 設計時に「実装時確定」だった点は次のとおり確定（残置なし）:
  ① **deprecated-api はパターン定義の正本ファイル `scripts/repo_scan.py` 自身を除外**——
  違反注入の実測で、paste-block のラベル文字列が自分のパターンに一致する自己偽陽性を
  発見した（定義は引用であって使用ではない。`LOG_EXIT_PREFIXES` と同じ境界の引き方 — §3.3）。
  ② **ts-react-web 列の サーバー側 `getSession(` は対象外の判断**——本列はブラウザ SPA で
  クライアントの `getSession()` は正規 API のため偽陽性>価値（Phase 15 の基準）。判断ごと
  カタログに記録し、SSR / Edge Functions を持つ列を起こす時にそちらへ載せる。
  ③ 検査5 のレイヤー定義は新設 BINDING `PLAN_LAYER_ROOTS`（カタログ表A「設計根拠の
  対象レイヤー」行）——`layer-violation` と同じ「列充填で有効化」の型。
- **決定点①は v2.8 で案A（hard 昇格＝G14「意図の保存」新設）に確定**——実装・同時改修・
  DoD の記録は Phase 19。soft 導入（v2.6）→ 昇格（v2.8）の順序自体はラチェット前例どおり
  （判断の主体はユーザー——決定点の建付けどおり）。
- 移植先での実体は DoD 実測: deprecated-api の違反注入→規則ID 1行で赤・除去で沈黙・
  未走査拡張子の注入→`binding-dead-pattern`・2秒予算内／人間 WIP ファイルへの Edit が
  ブロックされ commit / stash で自動解除・baseline 不在は警告付き素通し・**内部エラー
  注入（git 不在）でも通る**（§2c の fail-open は §2 と逆向きの注入——§2b と同様飛ばさない）
  ／レイヤー直下の新規ディレクトリ feat（plan 差分なし）で SOFT 警告1行・plan 差分ありで
  沈黙・コミットは常に通る（soft の実測）。

### Phase 18 — v2.7 同梱 ✅（red-first 証明 CI）（G10/G7）
- 契約と正本は §5 `red-first` ジョブ（`scripts/check_red_first.py`・BINDING は
  `repo_scan.py` の `SINGLE_TEST_COMMAND` / `SINGLE_TEST_CWD`——None なら不発＝
  列充填で有効化。免除は本文の `RED-FIRST-EXEMPT: 理由` 行——接頭辞は増やさない）。
  詳細仕様は §5 へ集約済み——本 Phase 節は残置しない。
- 設計時に「実装時確定」だった点は次のとおり確定（残置なし）:
  ① **worktree はリポジトリ直下の一時ディレクトリ**（`.red-first-*/`——.gitignore の
  キット区画へ追加）に作る——node/npx のモジュール解決は親ディレクトリを遡るため、
  主チェックアウトの `node_modules` が worktree からそのまま見える（システム temp に
  置くと実行環境の再構築という重い工程が要る）。
  ② **列の現実**: dart-flutter は多層構成（`app/` サブディレクトリでの実行）のため
  cwd スロット `SINGLE_TEST_CWD` を新設して吸収。rust は「該当なし＋代替」——モジュール内
  `#[cfg(test)]` の単独実行が構造的に不能（統合テスト限定の `cargo test --test <名前>` は
  版上げ候補としてカタログに判断ごと記録）。単一スロットのため複数列併用時は
  プライマリ言語の1列だけが配線し、配線外のテストは対象外として1行で見える。
  ③ **導入強度（決定点③）はスクリプトの `--soft` フラグに実装**——required 化は CI の
  呼び出しから1引数を外すだけ（`continue-on-error` 等、CI 実行環境の仕様に依存する
  仕掛けを使わない。表示のみでも内部エラー exit 2 は素通しにならない — Fail Loudly）。
  ※ 決定点③は v2.9 で required に確定した（Phase 21）——本 Phase の出荷形（--soft）は
  ロールバック手段として残る。
- DoD（キットで実測済み——移植先での実体も同じ注入）: ① 親でも緑のテストを fix に
  同梱 → `red-first-green` 1行（`--soft` で SOFT:＋exit 0・外すと HARD:＋exit 1）
  ② 正しい fix（親で赤）→ 証明1行＋exit 0 ③ `RED-FIRST-EXEMPT` 付き → 免除が1行で
  見える ④ 未配線 → 不発1行＋exit 0 ⑤ 追加テストなし fix・初回コミット → 対象外1行。

### Phase 19 — v2.8 同梱 ✅（feat⇔plan 対の hard 昇格＋G14「意図の保存」新設＝決定点①の確定）（G14/G7/G5）
- 契約と正本は §3.4 検査5（`HARD:feat-without-plan`・BINDING は `PLAN_LAYER_ROOTS` /
  `PLAN_DOC_PATTERNS`——空なら不発のまま＝列充填で有効化は据え置き）と .guardrails/GOALS.md レンズ4
  （G14「意図の複利」——fix⇔テスト G10＝回帰の複利の対）。詳細仕様は各正本へ集約済み。
- **決定点①はユーザー判断で案Aに確定**（v2.8）: G14 は判定列が書ける（レイヤー直下の
  新規ディレクトリ feat に根拠差分が同梱される——`feat-without-plan` がゼロ）ため新設可。
  soft の実績は v2.6〜v2.7 の同梱運用——昇格の判断主体はユーザー（決定点の建付けどおり）。
- **同時改修の3点セット**（旧 Phase 15〜17 節が予告していた「昇格時に必要」な改修——
  1つでも漏らすと G14 引用のコミットが検査3で偽陽性になる罠。すべて同一の変更で実施）:
  ① `check_commit_msg.py` の `GOAL_CITATION` を `G(1[0-4]|[1-9])` へ
  ② .guardrails/GOALS.md ヘッダ「G1〜G13」「13条」→「G1〜G14」「14条」＋レンズ4新設・G5 行の
  分担整理（同梱強制は G14 へ移管、G5 は「正本が単一」に純化）
  ③ README・本書・catalog 注記・CLAUDE.md テンプレの soft 表記を hard へ。
- DoD（キットで実測済み——移植先での実体は Step 5 ⑥）: ① レイヤー直下の新規ディレクトリ
  feat（plan 差分なし）→ `HARD:feat-without-plan` 1行＋exit 1（違反注入）
  ② plan 差分を足すと exit 0 ③ refactor: を名乗ると exit 0（逃げ道の意味論）
  ④ 列未充填 → 不発・初回コミット → 素通し（境界の据え置き確認）
  ⑤ 本文の `G14` 引用が検査3を通る・引用なしは落ちる（正規表現の同時改修の実測）。

### Phase 20 — v2.9 同梱 ✅（Stop ゲート条件B＝決定点②の強化案を確定）（G7/G4/G2）
- 契約と正本は §2b（条件A=未コミット作業・条件B=クリーンだが `dev.py check` 赤・
  免除=`BLOCKED:` 報告。ループ保護と fail-open は条件A/Bで共有）。詳細は §2b へ集約済み。
- **決定点②はユーザー判断で強化案に確定**（v2.9）。誤差し戻しのリスクは3つの絞りで
  抑える: ① `HARD:` を含む exit 1 だけが差し戻す（内部エラー・素の非0は素通し）
  ② uv / dev.py 不在は表示1行で条件Aのみへ縮退 ③ 上限3回のカウンタ（v2.4 から共有）。
  条件Bはクリーン時のみ走るため、毎ターンの追加コストは §7.7 の 2 秒予算内。
- DoD（キットで実測済み——手動 JSON 注入。移植先の実体は Step 4 ⑥）:
  ① クリーン＋check 緑 → exit 0（カウンタ削除） ② クリーン＋HARD 違反注入 → exit 2＋
  規則ID入り文面（条件B） ③ ダーティ＋check 赤 → 条件Aの文面（Aが先行）
  ④ transcript に `BLOCKED:` → exit 0（免除は両条件共通） ⑤ check 内部エラー
  （exit 2）注入 → exit 0 ⑥ uv 不在 → 表示1行＋exit 0（⑤⑥は fail-open——§2 と
  逆向きの注入） ⑦ `stop_hook_active`＋カウンタ超過 → exit 0。

### Phase 21 — v2.9 同梱 ✅（red-first の required 化＋EXEMPT 乱用監視＝決定点③の確定）（G10/G7）
- 契約と正本は §5 red-first ジョブ（CI の呼び出しから `--soft` を外した——違反は exit 1
  で赤。`--soft` はロールバック手段として残置）とルート AGENTS.md §8 のレビュー規約。
- **決定点③はユーザー判断で required に確定**（v2.9）。計画の運用条件「最初から
  required にするなら `RED-FIRST-EXEMPT` の乱用監視をレビュー規約に足すこと」を
  二層で実装: **機械部分**＝理由の無い免除は不成立（通常判定を続行——1行で見える）、
  **人間部分**＝レビュー規約（AGENTS.md テンプレ §8: 理由の具体性・CI 上の再現不能性・頻度を点検）。
- **required の完成はリポジトリ設定まで**: ブランチ保護の required checks へ
  `red-first` を登録する（ワークフロー側からは設定できない——Step 9 ④ に組み込み済み。
  未登録でも違反 PR は赤い ✗ として見える）。
- DoD（キットで実測済み）: ① 違反（親でも緑）→ `HARD:red-first-green`＋exit 1
  ② 理由なし EXEMPT → 免除不成立1行＋通常判定続行（違反なら赤のまま）
  ③ 理由あり EXEMPT → 免除1行＋exit 0 ④ `--soft` 付き → SOFT:＋exit 0
  （ロールバック経路の残存確認）。

### Phase 22 — v2.10 同梱 ✅（AGENTS.md 可搬化＝保留項目のトリガー発動）（G13/G5/G7）
- **トリガー成立の記録**: 「Claude Code 以外のエージェント（Codex / Cline 等）の併用が
  実際に発生した時」——ユーザー宣言により成立（v2.10）。登録済みの設計スケッチどおり
  **二分（移設）であって複製ではない**形で実装した。契約と正本は §6。
- 実装: ① `AGENTS.md.template` 新設（旧 CLAUDE.md.template の全章 §0〜§13 を移設・
  章番号不変。§10-4 はエージェント非依存に再構成——Claude Code フック固有の説明は
  CLAUDE.md 側へ） ② `CLAUDE.md.template` を薄い層へ書換（冒頭 `@AGENTS.md`＋フック層の
  説明のみ） ③ `AGENTS.md` を `missing-required` へ・インポート行を
  `agents-import-missing`（hard・`REQUIRED_CONTENT_RULES` の既定1件目）へ ④ 本書・
  .guardrails/GOALS.md・catalog・スクリプトの章参照を `AGENTS.md §N` へ機械改名（章番号不変のため
  1対1置換。移植元原本への言及と変更点の歴史記録は除外）。
- **実装時の事実確認（v2.10 時点の外部裏書き——変わったら本節を更新）**:
  Claude Code は AGENTS.md を直読みせず、`@AGENTS.md` インポートが公式ドキュメント記載の
  手段（ネイティブ対応要望 #6235 は 5,200+ 反応で未実装）。Cursor / Windsurf / Cline は
  ルート AGENTS.md のネイティブ読込を提供済み。Codex は AGENTS.md 標準の本家。
  symlink 方式（`ln -s AGENTS.md CLAUDE.md`）は Windows でプレーンテキスト化する既知の
  罠があり不採用（§7.2 の Windows 前提）。
- **同期スクリプトの不採用（判断ごと記録——再提案ループ防止）**: 「CLAUDE.md を編集したら
  Codex / Cline 用ファイルへ同期するスクリプト」は、同一内容の正本を2つ作った上で
  一致を機械が追いかける構図＝ binding-drift の規約版であり G5 違反。分割なら同期対象が
  存在しない——検査（`agents-import-missing`）は「同期」ではなく「構造の不変条件」を守る。
  Cline 固有の `.clinerules` 等のツール別ルールも同梱しない（各ツールが AGENTS.md を
  直読みする今、増やす価値 < ドリフト面。真にツール固有の規則が生まれた時だけ
  そのツールのファイルに書く——CLAUDE.md と同じ整理）。
- **対象外の境界（1行で明示）**: フォルダ別 CLAUDE.md は据え置き——各エージェントの
  自動探索仕様が割れる領域（Claude Code=CLAUDE.md 自動読込／Codex=入れ子 AGENTS.md）で、
  運用は AGENTS.md §12 手順3「触るフォルダの CLAUDE.md を読む」の指示で全エージェントに
  効く。入れ子 AGENTS.md 対応が実際に必要になったら版上げで検討。
- DoD（実測済み）: ① AGENTS.md 欠落 → `missing-required` 赤 ② CLAUDE.md にインポート
  行なし → `agents-import-missing` 赤・行を足すと沈黙（違反注入） ③ 両テンプレから
  作った状態で check 緑 ④ 章参照の残存 grep 0件 ⑤ 出荷状態の想定出力が §3.3 の
  5件と一致。

### Phase 23 — v2.11 同梱 ✅（MCP 採用許可リスト＝2026-07-07 調査の判定を門に固定）（G3/G5/G7）
- 契約と正本は §3.3 `mcp-not-allowed`（データの正本 = `repo_scan.py` の
  `MCP_ALLOWED_SERVERS`——中立既定値 `{"playwright"}`）・§12.4 の採用規律・カタログの
  「MCP・エコシステム採用規律」注記（ゲート3条の正本）。
- **2026-07-07 の MCP・エコシステム調査の要約（判定の出典）**: 現構成（Playwright MCP
  1本＋CLI 群＋薄い常駐）は推奨形に既に一致し、**即時採用すべき新規はゼロ**。
  継続採用 = Playwright MCP（操作レール §12.4・Web 列のみ。実ブラウザ操作は CLI で
  代替不能な唯一の領域）。不採用 = Serena（memories が §13 中央メモ禁止と衝突・
  STRUCTURE.md と役割重複・効果の実測が割れる）／GitHub MCP（`gh` CLI が完全代替——
  定義常駐 42〜55k トークン・実測約35倍差・注入実証事例）／Supabase・Postgres 系
  （`dev.py db` と CLI で充足・書込ツールは門の外の変更経路）／filesystem 等の基本系・
  sequential-thinking（ネイティブ重複）／memory 系（§13）／プロンプト集型・plugins に
  よるキット配布（規約が同一コミットに固定されない——G5/G1）。保留4件はトリガー付きで
  上記保留節に登録。詳細な判定表と情報源は README v2.11 の不採用記録が転記先。
- **境界（1行で明示）**: 検査対象は**プロジェクト正本（追跡された .mcp.json）だけ**。
  タスク単位のローカル追加（`claude mcp add`——Chrome DevTools MCP 等の保留運用形）は
  追跡外＝自由。門は「常駐の既成事実化」だけを塞ぐ。
- DoD（実測済み）: ① playwright のみの .mcp.json → 沈黙 ② 許可外サーバー追加 →
  `HARD:mcp-not-allowed` 1サーバー1行（違反注入） ③ 解釈不能な JSON →
  `SOFT:mcp-unparseable` で素通し ④ .mcp.json 無し → 不発（出荷状態の想定出力は
  Phase 22 の5件から不変） ⑤ 2秒予算内。

### Phase 24 — v2.12 同梱 ✅（ブートストラップ監査＝実行規律1〜4の機械化。虚偽✅の門）（G7/G4/G2）
- 動機: 「LLM がプロンプト1つでキットを展開できるか」という懸念。
  弱点は実行規律1〜4が**心得のまま**で、✅ が自己申告だったこと。契約と正本は §3.5
  （台帳 `.guardrails/BOOTSTRAP.md`＋監査器 `check_bootstrap.py`・規則ID 4種）。
- **プロンプト分割の不採用（判断ごと記録——再提案ループ防止）**: プロンプトを複数に
  分けるのは「心得の再配置」であり、検証力を足さずに人間の介入回数だけを増やす
  （分割されたプロンプトの中でも LLM は同じようにサボれる）。正しい分割単位は既に
  **1 Step = 1 コミット**として存在し、その完了主張を本 Phase の門が検証する——
  結果として人間は台帳（.guardrails/BOOTSTRAP.md）を見るだけで進捗を監査できる＝分割の利点
  （チェックポイント）はプロンプトを分けずに得られる。なお人間が任意に「Step N まで」と
  区切って依頼する運用は従来どおり可能（門は区切り方に依存しない）。
- DoD（実測済み）: ① 出荷状態（全 🚧）→ 沈黙 ② Step 0 を刻印なしで ✅ →
  `bootstrap-false-done`・Step 1 を ★ 残置で ✅ → 同（違反注入2系統） ③ 順序違反
  （Step 1 が 🚧 のまま Step 2 を ✅）→ `bootstrap-order` ④ 2 Step 同時 ✅ →
  `bootstrap-multi-flip` ⑤ ✅→🚧 差し戻し → 許可・✅→— → `bootstrap-demote`
  ⑥ — の備考なし → `bootstrap-ledger` ⑦ 導入済みスクラッチで Step 0〜5 の正当な
  ✅ 積み上げ → 各コミットで監査 PASS。

### Phase 25 — v2.13 同梱 ✅（feat-without-test・soft——著名キット調査②の採用1）（G10/G4）
- 出典: **2026-07-07 調査②（著名な同種キット）**。Superpowers（obra——公式マーケット
  プレイス収載・数万 star）は RED-GREEN-REFACTOR を鉄則化し「テスト前に書かれたコードは
  削除」とまで規定する。本キットは fix 側（検査2 hard＋red-first CI 証明）のみ機械化済みで
  **feat 側が空白**だった——ここを埋める。ただしプロンプト層の「鉄則」は破れる
  （調査②の Fowler 検証・EPAM 事例が実証）ため、本キットでは commit-msg の門に置く。
- soft で導入する理由と**昇格トリガー**: テスト不要な feat が正当に存在し偽陽性率が
  未知（検査5の v2.6→v2.8 と同じ経路）。トリガー = 数 Phase 分の運用で偽陽性の頻度を
  観察した後、逃げ道の設計（refactor/chore を名乗る or `TEST-EXEMPT: 理由`）とともに
  hard 化を判定する。
- DoD（実測済み）: ① feat＋コード変更＋テスト無し → SOFT 1行・exit 0 ② テスト同梱 →
  沈黙 ③ docs のみの feat → 沈黙（コード条件） ④ fix 側の検査2は従来どおり hard。

### Phase 26 — v2.13 同梱 ✅（commit-too-large・soft——著名キット調査②の採用2）（G11/G4）
- 出典: 調査②の収斂点——Superpowers は plan を「**2〜5分粒度のタスク**」に割ることを
  強制し、各タスクをコミットにする。大きな塊は検証の追跡可能性（どの門が何を検証したか）
  を壊す——実行規律2の一般開発版。純変更行数（生成物・lockfile 除外）の soft 上限
  （既定 400・列上書き可）として可視化する。hard にしない理由は §3.4 検査7 に記録
  （初回移植・一括リネーム等の正当な大型コミット）。
- DoD（実測済み）: ① 401行の注入 → SOFT 1行・exit 0 ② 400行以下 → 沈黙
  ③ STRUCTURE.md・lockfile の巨大 diff は数えない（除外の実測） ④ 予算内。

### Phase 27 — v2.14 同梱 ✅（kit-source-exempt＝キット原本自身の Stop ゲート永久赤の解消）（G9/G4/G7）
- 経緯: このキット原本リポジトリを GitHub へ公開する際、Stop ゲート（§2b 条件B）が
  `missing-required`(AGENTS.md/CLAUDE.md) と `agents-import-missing` の HARD で
  恒久的に赤止まりした。§3.3 の「出荷状態の想定出力」はこの3件を**導入先が Step 1 で
  解消する前提**で正常扱いしていたが、キット原本自身は Step 1 を実行する主体ではない
  （実体化は導入先プロジェクト固有の仕事）ため、この前提が成立しない。
- 検討: 「原本自身にも AGENTS.md/CLAUDE.md を実体化する」案は、キットの立場（規約2文書は
  導入先固有の内容を書く場所——§6）と矛盾するため不採用。「Stop フック側だけ特別扱いする」
  案は、`check_structure.py` 自体の exit コードは赤のままになり `dev.py check` を呼ぶ他の
  文脈（CI 等）との整合が崩れるため不採用。
- 採用: 構造だけでは「キット原本自身」と「導入先が Step 1 未着手なだけ」が同型で見分けが
  つかない（推測禁止 — §7.4 の近似は仕様と異なり、ここは判定を誤ると HARD が消える側の
  リスク）ため、**配布物には複製されない明示マーカー**を新設した:
  `.guardrails-kit-source`（`install_kit.py` の `META_FILES` に同居——バイトコピーされる
  `scripts/repo_scan.py` 自身にフラグを持たせると導入先にも複製され判定が骨抜きになる
  ため、「配布されないファイルの有無」という構造的シグナルに倒した — G9）。
  `repo_scan.is_kit_source_repo()` がこのマーカーを見て、`check_structure.py` の
  `missing-required`(AGENTS.md/CLAUDE.md) と `agents-import-missing` だけを SOFT へ
  降格する（他の必須ファイル・他規則は無傷——キット原本もそれ以外の防壁は全部満たす）。
- DoD（実測済み）: ① マーカーを一時退避 → 3件とも HARD に復帰・exit 1
  （導入先と同じ挙動が確認できる） ② マーカーを戻す → 3件とも SOFT・exit 0
  ③ `install_kit.py` のマニフェスト生成にマーカーが含まれない（導入先に複製されない）
  ④ AGENTS.md/CLAUDE.md 以外の `missing-required` 対象を欠落させても HARD のまま
  （降格対象を2件に限定できている）。

### Phase 28 — v2.17 同梱 ✅（context-doc-too-large・soft——調査③の採用）（G3/G9）
- 出典: **2026-07-07 調査③（ゼロレビュー・自律運用系——ユーザー提供の外部リサーチを
  一次入力として判定。judgment の正本は `surveys/SURVEY_ZERO_REVIEW.md`）**。
  採用2件（本検査＋テンプレ §8 の Testing Trophy 心得2行）・保留1件（依存・脆弱性監査
  CI ジョブ——上記保留節）・不採用7群（自己治癒ランタイム=門の外の変更経路の極致／
  Dark Factory 型自動マージ=統治層の外、ただし Validator≒本キットの CI という整理を記録／
  Telos 型関数単位注釈=形式強制は偽陽性>価値／SOUL・MEMORY・HEARTBEAT=§13 再確認／
  Vibe Testing=非決定な検証は門になれない／トークンバジェット・決定テーブル=対象外だが
  中核思想の外部裏書き／SPEC.md・worktree=調査②再確認）。
- キットの立場の1行固定: **ゼロレビューが買えるのは「機械検査可能な違反ゼロ」まで**。
- DoD（実測済み）: ① 201行の CLAUDE.md 注入 → SOFT 1行・exit への影響なし ② 200行
  ちょうど → 沈黙（境界） ③ フォルダ CLAUDE.md にも効く ④ AGENTS.md は 500 行境界
  ⑤ 出荷状態の想定出力は5件のまま不変。

### Phase 29 — v2.18 同梱 ✅（env-file-tracked・hard——調査④の採用1）（G7/G9）
- 出典: **2026-07-07 調査④（門主導アーキテクチャ群——判定の正本は
  `surveys/SURVEY_GATE_ARCHITECTURES.md`）**。レポートの大半は現行機構の外部裏書き
  （RADAR≒機械の門>人間レビューの実測・PreToolUse≒§2・ペナルティルール≒HARD/SOFT
  二値の下位互換・ループ遮断器≒§2b 回数上限）で、本物の空白が2つ——本 Phase と Phase 30。
- 契約は §3.3。gitleaks の**内容**検査を補完する**存在**検査（must ティアの機械化）。
- 複雑度ゲートは**自作せず**、catalog 注記「関数複雑度ゲートの対応表」に正本化
  （linter の AST が上位互換——重複排除ゲート。Step 6 lint 昇格時の推奨）。
- DoD（実測済み）: ① .env を追跡 → HARD 1行 ② .env.local → HARD ③ .env.example →
  沈黙 ④ 出荷状態の想定出力は5件のまま不変。

### Phase 30 — v2.18 同梱 ✅（test-shrink・soft——調査④の採用2）（G10/G4）
- 契約は §3.4 検査8。**red-first の外にあった空白**: red-first は「新テストが親で赤」を
  証明するが、既存テストの assertion 削除で緑にする経路は未監視だった（Clean Room QA の
  脅威モデル）。soft の理由と Clean Room 保留のセンサー役は §3.4 に記録。
- DoD（実測済み）: ① fix でテスト純減 → SOFT 1行・exit 0 ② 純増 → 沈黙 ③ 列未充填 →
  不発 ④ docs: 件名 → 対象外。

### Phase 31 — v2.19 同梱 ✅（missing-log-coverage・soft——ログ被覆の機械化）（G9/G7/G4）

- 経緯: セッション内の対話（「全関数にログを強制すべきか」「重要度は誰が決めるか」）から
  出発。結論: **重要度判定は機械化できない**（意味判断であり構文検査の範囲外）。全関数への
  一律強制は不採用（ノイズで信号対雑音比が悪化する上、空呼びで簡単に骨抜きにできる）。
  「テスト実行時の出力量で自動的にログのON/OFFやコード上の位置を変える」案も検討したが、
  ①出力量と重要度は無相関（ホットパスほど出力が多く逆効果）②テスト実行の偶発性が
  G1決定性と衝突③レビューを経ないソース変更＝`SURVEY_ZERO_REVIEW.md` が却下した
  「自己治癒ランタイム」と同型、の3点で不採用（詳細は §8.4）。
- 採用: 対象を「重要度」でなく**客観的に検出できる境界**（I/O・外部呼び出し・エラー
  ハンドラ）に絞り、境界の前後で `logOp` 呼び出しか `NO-LOG: 理由` コメントのどちらかを
  要求する存在検査。理由の妥当性は検証しない——RED-FIRST-EXEMPT と同じ境界。
- 外部調査で裏付け（2026-07-08）: ESLint `eslint-comments/require-description`・Rust
  clippy `allow_attributes_without_reason`・SonarQube S108/S2486・Honeycomb の DBマイグレーション
  linter（`atlas:nolint` 注釈・監査プロセスは「特に無し、人を信頼する」と公式ブログで明言）
  ——いずれも「存在検査＋可視化」止まりで、理由の中身までは検証していない。この設計は
  発明ではなく実務で通用している定石の踏襲。Microsoft Research の産業調査（ICSE 2014,
  Fu et al.）も、実際のログ配置は全関数のごく一部に留まることを実測している。
- soft で導入する理由: `LOG_BOUNDARY_PATTERNS`（境界検出）は行指向の近似であり、対象
  言語ごとの偽陽性率が未知（`feat-without-test` の v2.13→v2.13 と同じ経路）。列充填時に
  実測してから hard 昇格を判断する。
- DoD（実測済み・シミュレーション列で注入）: ① 境界行のみでログ被覆なし → SOFT 1行
  ② `logOp(...)` が前後5行以内にある → 沈黙 ③ `NO-LOG: 理由` コメントがある → 沈黙
  ④ `LOG_BOUNDARY_PATTERNS` 未充填（キット原本の現状） → 不発・5件SOFTの基準線に影響なし。

### Phase 32 — v2.22 同梱 ✅（guard コーパス性能是正——プロセス起動回数の削減）（G11/G7）

- 経緯: 導入先プロジェクト（Windows・32論理コア機）で、`guard-corpus` フックが
  pre-commit チェーンの中で断続的に失敗（`guard が10秒以内に返らない`）。単体実行では
  安定して通るが、他のフックと並走する文脈でだけ落ちる——2回連続失敗を実測し、
  ルート AGENTS.md §10-4 の規律どおりリトライを止めて原因調査に切り替えた事例が発生し、
  本キット側で再現・実測した。
- 実測: ① `check_guard_corpus.py` 単体実行でも Windows 32コア機で一貫して8〜9秒
  （§7.7 の旧予算「2秒以内」を約4倍超過）② ワーカー数を1〜48で振った実測で、
  旧実装（`min(32, max(8, 2×コア数), 行数)`）が選ぶ32並列は、8並列と同等かそれ以下——
  「物理コア数より多めが有利」という旧コメントの前提は誤りで、ボトルネックは
  bash/jqプロセス起動自体のOSコストだった（32コア機では常に上限32が選ばれ、
  「プロセス嵐の抑止」という上限の意図が機能していなかった）③ `guard_git_bypass.sh`
  を読み、1回の呼び出しで `grep`/`sed`/`tr`/`jq` が10〜18回起動していることを特定
  （典型的な `git commit -am` で実測 約1073ms/回）④ Windows実機で `bash -c 'true'`
  単体は約44ms/回——ボトルネックはbash起動そのものではなく、内部のプロセス起動の
  カスケードだった。
- 対応: ①`check_guard_corpus.py` の並列度上限を32→12へ下げる（実測: 8並列で頭打ち・
  24並列では旧実装は逆に悪化）②`guard_git_bypass.sh` 本体の `grep -Eq`/`grep -q`
  直呼びを bash 組み込みの `[[ =~ ]]`／`[[ == * ]]`／パターン展開へ置換し、
  `\b`（単語境界）は MSYS2/Windows の bash 正規表現エンジンが非対応と判明したため
  POSIX標準クラスのみで再実装（`word_present()` ヘルパー — `(^|[^[:alnum:]_])word
  ([^[:alnum:]_]|$)`）。jq（JSON解析）と sed（引用符除去の可変長置換）の2個だけ残置——
  安全な組み込み代替が無く、量的にも支配的でないため。jq 不在時の保守的経路（生JSON
  マッチ）は corpus 再生で経路が通らないため変更対象外。
- 実測（是正後）: ① 全74行 PASS を5回連続確認 ② 1回あたりの呼び出しコストが
  約1073ms→約243ms（4.4倍）③ 全行再生は8〜9秒→5〜8秒 ④ **是正の過程でコーパスが
  実際に規範として機能した**——書き換え直後は`\b`非対応により36/74行が不一致になり
  （DENYがALLOWへ後退）、コーパスがこれを機械的に検出して修正に至った（G10「回帰の複利」
  が門番自身の改修にも効いた実例）。
- 境界: `guard_git_bypass.sh` の「jq 不在時の保守的経路」（生JSON直接マッチ）は
  corpus 再生の対象外（`check_guard_corpus.py` は jq を必須ツールとして要求するため
  この経路を通らない）——今回は変更していない。触るなら別コミットで同種の実測を要する。

### Phase 33 — v2.23 同梱 ✅（guard フックの言語移行——bash→Python）（G11/G5/G7）

- 経緯: 「他にも同種の遅い実装が無いか」「そもそもbash採用に根拠はあるか」という
  観点から全フックを棚卸しし、旧 `guard_git_bypass.sh`（v2.22是正後でも
  jq・sedの2プロセスが残存・約243ms/回）を Python へ完全移行して実測した。
- 判断の軸: 「Go/Rustも候補に入れてセットアップ時に最速を実測選択する」案も検討したが
  不採用——実装が使用言語の数だけ増えるとG5「単一の正」に反し、Step 0にコンパイル・
  ベンチマーク工程を足すとG13「移植の定数時間」に反し、Go/Rustのツールチェーンを
  キット自体の新規必須依存にするのは重複排除ゲート違反（このキットが唯一必須にする
  言語ツールは `uv` のみ）。Python は**既存の必須依存の範囲内**で完結する選択。
- 実測（`guard_git_bypass` → `.py`）: ①JSON解析（jq代替）・正規表現（grep代替）・
  引用符除去（sed代替）はすべて標準ライブラリで完結し子プロセスは0——唯一 dirty
  判定の `git status` だけ残る ②Windows実機で bash 版243ms/回 → Python版
  （`uv run python`）約150ms/回 ③`tests/guard_corpus.tsv` 全74行を10回連続PASS
  ④並列再生（コーパスチェッカ内部は `sys.executable` 直起動——同一 `uv run` プロセス内
  なので毎回 `uv run` を再度挟まない）で全74行0.4〜2.9秒（旧bash実装は5〜8秒）——
  §7.7 の「全行10秒以内」予算に対し実測は大幅な余裕。
- 発見した副産物のバグ2件（コーパス・手動検証それぞれで実際に検出——これ自体が
  検証機構の実例）:
  ① 初回移植で `sys.stdin` のUTF-8再設定を忘れ、日本語を含むコミットメッセージで
  JSON解析が壊れていた（`sys.stdout`/`sys.stderr`のみ再設定し`stdin`を漏らした）
  ② 検証用ハーネス側のバグ（本体ではない）——cwdをフィクスチャへ差し替える際に
  guardスクリプトを相対パスで渡すと、guard自身が見つからず「起動できない」が
  そのままDENY扱いに化けて誤判定になった。
- `guard_human_wip.sh`（PreToolUse: Edit|Write|MultiEdit——編集の度に発火する同格の
  ホットパス）も同様に Python 化。**専用の回帰コーパスが元々存在しない**フックのため、
  6ケースの手動比較（baseline該当+dirty=DENY／該当+clean=ALLOW／baseline無し=fail-open
  ALLOW／baseline対象外=ALLOW／file_path無し=ALLOW／session_id要サニタイズ=DENY）で
  新旧の exit code とメッセージ文言が完全一致することを確認。実測 593ms/回 → 230ms/回
  （2.6倍）。.guardrails/GUARDRAILS.md §2「所有権ガードのコーパス再生」の保留トリガー
  （guard_human_wip の改修発生）が本コミットで実際に発火したことを明記——
  `check_guard_corpus.py --hook` 拡張による恒久的なコーパス化は**未実施のまま残す**。
- 境界（このコミット時点でやらなかったこと）: `stop_incomplete_guard.sh`・
  `session_baseline.sh`・`post_edit_format.sh`・`post_edit_lint.sh` の4本は当初、
  優先度が低いと判断して見送った（Stop試行毎・セッション開始1回の頻度差、後2者は
  元々サブプロセス数が少ないという理由）。**`.claude/hooks/` 配下の言語統一
  （G5——実装言語という単一の正）を優先し、同一セッション内で Phase 34 として
  追加実施した。**
- 配布面: `install_kit.py` のマニフェストは `kit_root.rglob("*")` ベースなので、
  `.py` への拡張子変更も追加ファイル扱いとして自動的にマニフェストに含まれる
  （コード変更不要——実際に dry-run で `INSTALLED guard_git_bypass.py` を確認済み）。

### Phase 34 — v2.24 同梱 ✅（残り4フックの言語移行＋post-editツール呼び出しの是正）（G11/G5/G7）

- 経緯: Phase 33 で見送った残り4フックについて、`.claude/hooks/` 配下の言語統一
  （G5——実装言語という単一の正）を優先し、同一手順（実測→移植→検証→配線）で
  追加実施した。あわせて、フック本体をPython化しても呼び出す外部ツール
  （ruff/prettier等）が遅ければ効果が薄いという観点から、`post_edit_format.py`/
  `post_edit_lint.py` が呼ぶ外部ツールの呼び出し方も見直した。
- `stop_incomplete_guard.py`: 実測 約698ms/回→約157ms/回（3.5倍）。条件Bの判定
  （`dev.py check`）も `uv run scripts/dev.py check` の2段 `uv run`（dev.py 経由＋
  check_structure.py 経由）から `sys.executable` で `check_structure.py` を直接1段
  起動する形に変更——`dev.py` の `check` 動詞は列上書き不可・常に固定コマンドなので
  意味は変わらない。検証: dirty即差し戻し／clean+check未導入のfail-open／
  BLOCKED:免除／差し戻し上限3回、の4シナリオで新旧一致を確認。
- `session_baseline.py`: 実測 約356ms/回→約171ms/回（2.1倍）。移植直後、
  baselineファイルの書き込みがCRLFになる差分を検出（Pythonの`write_text`が
  Windowsでは既定で改行変換する——`newline="\n"`明示で修正）。修正後、baseline
  ファイルの中身がbash版とバイト完全一致することを確認。
- `post_edit_format.py`/`post_edit_lint.py`: bash の `case` 拡張子分岐を Python の
  `DISPATCH: dict[str, list[list[str]]]` へ置換。付随して、この2フックが**呼び出す
  外部ツール**の呼び方を実測してcatalog.mdへ反映した（詳細は`bindings/catalog.md`
  「post_edit フックの速度3原則」）: `npx prettier`（ローカルinstall済みでも約900ms/回）
  → `node_modules/.bin/prettier` 直接呼び出し（約240ms/回）／`uvx ruff`（約218ms/回）
  → `uv tool install ruff` 後の直接呼び出し（約156ms/回）。フック本体の言語より
  ここの差の方が大きい場面があることを実測で確認した。rust列の整形は
  `cargo fmt`（クレート単位・cwd切替要）から `rustfmt {file}`（単一ファイル直接・
  DISPATCHの素のargv実行と相性が良い）へ変更——post-editの「1ファイル」契約により
  合う形への改善でもある。
- Go/Rustをフック本体の実装言語として使う案は Phase 33 と同じ理由で再度不採用。
  post_edit フックが呼ぶ**外部ツール**をネイティブバイナリ（rustfmt・Biome等）に
  することとは別の話——フックの言語とフックが呼ぶツールの言語は独立（catalog.md
  「post_edit フックの速度3原則」に明文化）。
- 全6フックがPython化で揃ったことの記録: `guard_git_bypass.py`・`guard_human_wip.py`
  （Phase 33）・`stop_incomplete_guard.py`・`session_baseline.py`・
  `post_edit_format.py`・`post_edit_lint.py`（本Phase）。bash実装は0本になった
  （`.claude/hooks/` 配下はすべて `.py`）。

### Phase 35 — v2.25 同梱 ✅（NONDETERMINISM-EXEMPT——非決定性テストの免除機構）（G9/G1/G7）

- 経緯: 導入先プロジェクトで、実ブラウザがヘッダーとbodyを分割TCP書き込みするタイミング
  差を再現する回帰テストが、`test-sleep`（意図的な `sleep`）と `test-network`
  （意図的な `TcpStream`）の両方に違反として検出された事例が発生した。この種のテストは
  sleep・生ソケットの使用そのものがテストの本質であり、削除すれば再現できなくなる——
  §9.5 に「例外は目に見える形でのみ許す」という原則の記載はあったが、具体的な機構が
  無かった。
- 設計: `NO-LOG:`（§8.4）・`RED-FIRST-EXEMPT:`（§5）と同型の「存在検査のみ・理由必須・
  乱用監視はレビュー」境界を、`test-sleep`/`test-nondeterminism`/`test-network` の3規則
  共通の免除として追加した（3規則は同一テストで同時に発火しうるため、単一のコメントで
  まとめて免除できる設計にした）。判定は `missing-log-coverage` と同じ「境界行の前後
  N行以内」ウィンドウ方式（`NONDETERMINISM_EXEMPT_WINDOW`・既定3・列上書き可）——
  同一行限定にすると、sleep とネットワーク呼び出しが別行にまたがるテストで理由コメントを
  複製する必要が出るため。`test-calls-solver-direct` は対象外——既に
  `SOLVER_TEST_WRAPPER_NAME` の同一行検査という別の免除経路を持つ。
- 検証: 合成 rust フィクスチャで、免除コメント無し（`test-sleep`・`test-network` の
  2件検出）／免除コメント有り（0件）を確認。`check_guard_corpus.py`・
  `check_structure.py`（キット自身）に regressions 無し。
- 配布面: `scripts/repo_scan.py`（`NONDETERMINISM_EXEMPT_PATTERN`・
  `NONDETERMINISM_EXEMPT_WINDOW`）・`scripts/check_structure.py`（`check_tests`）・
  `AGENTS.md.template`・`.guardrails/CUSTOMIZE.md` を更新。

### Phase 36 — v2.29 同梱 ✅（所有権ガード回帰シナリオ導入——§10保留の解消）（G10/G7）

- 経緯: 本節の保留リストに「所有権ガードのコーパス再生」がトリガー待ちで登録されて
  いた（トリガー＝次にこのフックへ手を入れる時）。compact 時の再バランス誤爆
  （`source` を見ずに AI 自身の未コミット作業を人間 WIP と誤認し、以後の Edit/Write を
  ブロックし続ける — §2c）が実機事故として発生し、その修正のタイミングでトリガーが
  発火した。
- 設計: §2 の `guard_git_bypass.py` 用コーパス（`tests/guard_corpus.tsv`・1行=1コマンド）
  とは異なり、所有権ガードは「SessionStart→(dirty化)→SessionStart→PreToolUse」という
  複数手順そのものが検査対象で TSV1行では表現できないため、`scripts/check_ownership_guard.py`
  を新設し、シナリオを Python 関数として直接書く方式にした。6シナリオ: clean start
  即許可／人間 WIP のブロック／human の commit による自動解除／compact での AI 自身の
  WIP 誤認防止（今回の事故そのものの回帰テスト）／compact 時の既存人間 WIP 保護の
  維持／`source` 不明時の安全側フォールバック。`.pre-commit-config.yaml` へ
  `ownership-guard` フックとして配線した（`guard-corpus` と同型の `files:` 限定——
  門番3点に触れた時だけ通常コミットで走り、CI の `--all-files` では常時走る）。
- 検証: 修正前の `session_baseline.py`（親コミット相当）へ本テストを実行し、compact
  関連の2シナリオが実際に赤（ALLOW になるべき所で DENY）になることを確認。修正後は
  全6シナリオ PASS。
- 配布面: `scripts/check_ownership_guard.py`（新設）・`.pre-commit-config.yaml`
  （`ownership-guard` フック追加）。CI の `checks` ジョブは既存の
  `pre-commit run --all-files` を再実行するため、ワークフロー自体への追加変更は不要。

### Phase 37 — v2.30 同梱 ✅（commit-msg 系ゲートの CI 実効化——静かな不発の解消）（G9/G7）

- 経緯: Phase 36 の作業中に副産物として発見した。`check-commit-msg` は
  `stages: [commit-msg]` のため、CI の `checks` ジョブが実行する
  `pre-commit run --all-files`（`--hook-stage` 未指定）では実行されない——pre-commit
  本体の仕様として、明示しない限り commit-msg 段のフックは走らない。ローカルで
  `pre-commit install` していない限り、G引用必須・fix⇔テスト・依存宣言・feat⇔plan の
  全 HARD 検査が誰にも掛からない。本キット原本自身のこの working copy にも
  `pre-commit install` が未実行だったため、実際に気づかれないまま埋もれていた。
- 設計: `scripts/check_commit_msg.py` に `--base <rev> [--head <rev>]` モードを追加。
  base..head の非マージコミット1つずつを、`git worktree add <sha>` →
  `git reset --soft <sha>^`（HEAD だけ親へ戻し、index/working tree はそのコミットの
  スナップショットのまま）で「今まさに commit しようとしている状態」に再現し、単発形態
  （`main_single`）を検査ロジックの複製ゼロで再実行する（`check_red_first.py` の
  `ParentWorktree` パターンを踏襲）。`guardrails-ci.yml` に `red-first` と同型の
  `commit-msg-history` ジョブを追加（BINDING 不要——git と python のみで完結）。
- 副次発見: 実装中、`fix-without-test`（検査2）だけ兄弟検査（5/6/7/8）が持つ
  「`TEST_PATH_PATTERNS` 未充填なら不発」バイパスを欠いていることが判明した。列を
  1つも選んでいないリポジトリ（および言語なしで出荷される本キット原本自身）では、
  どんな `fix:` コミットも**原理上絶対に**この検査を通過できない状態だった——CI 実効化
  で初めて実害が顕在化する前に是正（§3.4 検査2）。
- 検証: 一時 git リポジトリで (1) 本物の空 `TEST_PATH_PATTERNS`・テスト無し `fix:` →
  バイパスで exit 0 (2) パターンを充填したコピーで実質的な `fix:`（テスト無し）→
  従来通り exit 1 (3) 同コピーでテストファイルを同梱 → exit 0、の3通りを確認。
  履歴再検査モード自体も、このブランチの実コミット5件（`origin/master..HEAD`）を
  `--base origin/master` で再検査し全PASSを確認、さらに合成リポジトリで
  G引用漏れのコミットを1つ作り、それが `HARD:commit-msg-history-mismatch` として
  正しく検出されることも確認した。
- 配布面: `scripts/check_commit_msg.py`（history モード追加）・`.gitignore`
  （`.commit-msg-history-*/` 除外）・`.github/workflows/guardrails-ci.yml`
  （`commit-msg-history` ジョブ新設）。

### Phase 38 — v2.32 同梱 ✅（binding-dead-path——パス型バインディングのドリフト検出）（G9/G7）

- 経緯: キット類似構成の導入先プロジェクトで、単一出口ログファイルのパスが lint 設定・
  `repo_scan.py` の充填値（`LOG_EXIT_FILES`）・カタログ列の3箇所に散在した状態で
  ディレクトリ整理が行われ、破壊の見え方が非対称であることが実測で顕在化した——
  lint 設定は移動先で即座に赤になるが、repo_scan 側のパス/prefix 型バインディングは
  一致対象を失っても無反応。とりわけ `FFI_BOUNDARY_FILE_PATTERNS`（missing-catch-unwind）・
  `PLAN_LAYER_ROOTS`（feat-without-plan）・`LAYER_FORBIDDEN_IMPORTS`（layer-violation）・
  `ORPHAN_UNIVERSES`（orphan-file）はレイヤー直下の改名1つで検査ごと静かに消える
  （fail-open の最悪形 — G9。なお `LOG_EXIT_FILES` 自体は移動先の print 直呼びが
  `log-direct-call` で落ちるため fail-closed だが、剥がれた値は残置される）。
  「このファイルを動かすなら他の箇所も見ろ」という近接コメント（心得）ではなく
  機械検査に倒す——§6 注記の設計判断（門は心得でなく検査側）と同じ整理。
- 実装: `check_structure.py` に `check_binding_dead_paths` を追加。パス/prefix 型
  バインディング5種のうち追跡ファイルに1件も一致しない値を `SOFT:binding-dead-path`
  1値1行で警告（prefix の重複は排除——ts 列の `ORPHAN_UNIVERSES` は同一 prefix を
  .ts/.tsx で2回持つ）。soft の理由は §3.3 の規則注記のとおり（ブートストラップ途中の
  正当な一時状態と区別不能——binding-unstamped と同じ「見える猶予」）。
- DoD（実測済み）: ① 5種すべてに実在しないパス/prefix/パターンを注入 → それぞれ
  `SOFT:binding-dead-path` 1行（計5行・重複 prefix は1行に集約） ② 実在パスのみに
  戻す → 沈黙 ③ キット原本の `check` は既定5件 SOFT・exit 0 のまま不変（出荷状態の
  想定出力に影響なし——中立既定値は全スロット空のため不発） ④ フルスキャン 179ms
  ＝性能予算内（§7.7）。

### Phase 39 — v2.34 同梱 ✅（violation ledger——門が止めた事象の機械記録）（G4/G9）

- 経緯: 「経験を言語ルールとして蓄積し AI に読ませる」系の運用（振り返り→CLAUDE.md 昇格）
  との比較検討で、本キットの欠落が1つ特定された——git 履歴は通ったものしか残さず、
  **門が止めた事象と無視された soft 警告はどこにも記録されない**。soft→hard 昇格の
  既存プロセス（`feat-without-plan` v2.6→v2.8 の「数タスク実測して偽陽性率を確認」）の
  実測が逸話頼みだった。比較検討の結論はキットの語彙で: 観測データの**記録（第1層・事実）
  は機械が担い**、意味づけ・同型判定・昇格提案の自動化（上層）は原理的に揺れるため
  門に入れない——LLM の失敗要約を事実として蓄積する経路は虚偽✅（§3.5）と同型の汚染。
- 実装: 契約・スキーマ・記録しない境界（コーパス再生/probe の抑止・履歴再検査の worktree
  隔離・CI）は §3.6 が正本。書き手2実装（`repo_scan.append_violations`＋フック側
  `record_block`——依存ゼロ前提のための独立最小実装・スキーマ変更は同一コミット）。
  check_commit_msg は8箇所の違反 print を `_emit`（表示＋記録バッファ）へ集約した。
- 不採用（判断ごと記録——再提案ループ防止）: ① **集計・昇格提案の自動化**（「30日N回で
  昇格を提案」等）——解釈層は門に入れない。集計はアドホックで足り、昇格は人間承認
  （§3.6）。② **コマンド実行ログの全記録**（exit code・stderr 指紋から失敗を採掘する案）
  ——exit code ≠ 失敗（red-first は落ちるのが成功）・「同じ失敗か」の同型判定は意味解釈で
  揺れる・既知の重要工程は dev.py の正規入口（G2）が前手で塞いでおり主な獲物が残らない。
  ③ **probe の DENY 記録**——probe は事前照会という正規経路（規律に従う行動）であり、
  記録すると正しい振る舞いほど「迂回試行」に見える逆転が起きる。
- DoD（実測済みは同コミットのメッセージに記録）: ① check（既定5 SOFT）→ ledger に
  stage=check-structure の5行 ② 不正メッセージの commit-msg 検査 → HARD 1行が追記
  ③ guard へ `git commit --no-verify` を stdin 注入 → stage=guard の DENY 1行
  ④ コーパス全行再生 → ledger の行数不変（抑止の実測） ⑤ probe → 不変
  ⑥ 書き込み不能時 → stderr 1行・exit code 不変。

### Phase 40 — v2.35 同梱 ✅（Step 9 ④ 外部設定の実測検証——監査の空白の解消）（G7/G9）

- 経緯: 外部レビューで「ブランチ保護・required checks・push 権限はリポジトリ外の設定で
  あり、キット単体では保証できない」という指摘を受けて突き合わせたところ、キットは
  Step 9 ④ でこの設定を**規定**し（v2.9・Phase 21「required の完成はリポジトリ設定まで」）、
  文書にも明記していたが、`assert_step_9` はリポジトリ内のファイルしか見ておらず
  **④ だけが check-bootstrap の監査の空白**だった——「規定済みだが未検証」は §3.5 が
  塞いだ虚偽✅の外部設定版。
- 実装: `verify_required_checks`（契約は §3.5 の Step 9 注記が正本）。fail の向きの2段
  （検証できて不在=失敗／検証不能=表示して素通し）が設計の核心——ネットワーク・認証に
  依存する初のアサーションのため、オフラインの日にブートストラップを止めない側へ倒し、
  素通しは必ず1行表示する（G9: 静かなスキップ禁止）。CI の再監査は checks ジョブに
  `GH_TOKEN: ${{ github.token }}` を配線して認証（ルールセット照会は読み取り権限で足りる。
  旧来ブランチ保護の照会は admin が要るため CI では照会不能→ルールセット側だけで判定）。
- DoD（実測済み）: ① 実リポジトリ（GitHub リモート・保護なし）→「必須チェック実測: なし」
  の失敗1行（実 API 照会） ② gh 不在 → 表示1行・素通し ③ API 到達不能 → 表示1行・
  素通し ④ GitHub 以外のリモート → 検証対象外1行・素通し ⑤ 台帳全 🚧 のキット原本 →
  アサーション不発・exit 0 不変。
- **是正（v2.36——外部レビュー起点の再検証で発見した偽陽性）**: 初版は「どちらか一方でも
  確定回答があれば verified」とし、rulesets が確定回答（200・required なし）で旧来保護が
  照会不能（403）のとき「検証できて不在」と誤断定していた。CI の GITHUB_TOKEN では旧来
  保護の照会が**常に** 403（admin 必須）のため、旧来保護だけに登録した採用先は CI 再監査が
  **必ず偽赤**になる構成だった。修正: 発見すれば片系統でも合格（存在証明）・不在の断定は
  両系統の確定回答が揃った時のみ・断定不能は表示して素通し（どの系統を照会できなかったか
  を明示）。同時に、当初の手動 DoD（1回きりの注入）を `--verify-scenarios`（全モック
  8シナリオ・ネットワーク不要）へ昇格し、pre-commit の `bootstrap-verify-scenarios`
  （`files: ^scripts/check_bootstrap\.py$`——guard-corpus / ownership-guard と同じ
  「門番自身の回帰」の型）で固定した。シナリオ4が本偽陽性の再発防止。
- **是正2（v2.37——required 最低線）**: v2.36 時点では最低線を `red-first` のみとし
  「`checks` / `commit-msg-history` はローカル門と重なるため要求水準はプロジェクト判断」
  と記録したが、外部レビュー2巡目の指摘でこの根拠の誤りが確定した——「重複」が成立する
  のはローカルフックが動く経路だけで、**CI を最終防衛線とする主張（§5・README）の対象
  経路（Web 編集・フック未導入マシン）では、この2ジョブが唯一の強制点**。required で
  なければ赤のままマージでき、最終防衛線の主張が虚偽になる。最低線を3コアジョブへ変更し、
  シナリオを10本へ拡張（「red-first と checks のみ → 不足で失敗」「2系統に分かれて合計
  3ジョブ → 合格」「一部確認+片系統照会不能 → 断定せず素通し」を追加）。
- **受入検証の残（実機未検証——§2d の検証根拠タグと同じ扱い）**: 「CI 上の GITHUB_TOKEN
  が `/rules/branches` に確定回答する（contents: read で足りる）」は公式ドキュメント根拠で
  あり、実 CI での確認はまだ無い。モック10本が固定するのは分岐ロジックまで。確認の
  トリガー = rulesets を登録した最初の採用先（または本リポジトリの PR）で、CI 再監査の
  ログが fail-open の表示ではなく確定判定になっていることを見る——確認したら本注記を
  実測済みへ更新する。

### Phase 41 — v2.38 同梱 ✅（更新経路の整備——導入済みリポジトリへの新版反映）（G13/G9）

- 経緯: 導入済みリポジトリへ新版キットを反映する経路が未整備だった。機械配置の土台は
  既存——インストーラの `UPGRADED` 判定（キット系統＋追跡済み＋クリーン → 上書き・
  **git 履歴が安全網**）で「粗い更新」は元から動く。欠けていたのは ① KEPT 検証条項の
  版追随（新フックが旧設定を素通りして静かに届かない——`installer-token-drift` として
  門化・§3.3。実測: ownership-guard / codex-hooks が2版の間 `PRECOMMIT_REQUIRED` から
  漏れていた） ② 丸投げの入口（更新プロンプト）。
- 実装: `PROMPT_claude_code_update.md`（Step U0〜U6）。設計の要点:
  - **版ファイルは作らない**（G5——正本は git タグ）。更新差分の機械入力は本書 §10 の
    **Phase 見出し**（追記専用の連番）——旧 GUARDRAILS（`git show HEAD:`）との diff で
    「何が増えたか」が計算できる。
  - **復元の向き**: UPGRADED で消えた採用先ローカル部（BINDING 充填・COMMANDS・列ジョブ・
    §10 の自リポジトリ状態）は、**新版ファイルを土台に旧版から充填だけを移植**する。
    旧区画を丸ごと戻すのは禁止——新版で増えたスロットが消えると検査器ごと落ちる。
  - 一時停止中の規則（清掃 Phase）は更新で再有効化しない（清掃 Phase の仕事のまま）。
- 不採用→保留（判断ごと記録）: **BINDING 域温存の機械マージ**は初案の「旧区画を新版へ
  移植」が上記のとおり向きが逆で危険（例: v2.19 より前の区画を後へ移植すると
  `LOG_BOUNDARY_PATTERNS` が消えて check_structure が AttributeError で落ちる）。
  安全に機械化するには充填ブロックのマーカー包みという貼り方の規約変更が要る——下の
  保留に登録。
- DoD（実測済み——installer-token-drift 側の注入・フィクスチャは同コミットのメッセージに
  記録）: 更新プロンプト自体は文書のため、実測は最初の実更新で行い結果をここへ追記する。

### Phase 42 — v2.39 同梱 ✅（fix-without-test のインラインテスト対応——誤ブロックの是正）（G10/G13）

- 経緯: 採用先 Rust リポジトリからの還元。同一ファイル内 `#[cfg(test)] mod` 形式のみを
  変更する `fix:`（チェッカー単独で完結し、パス判別に一致する生成器・統合テスト側の変更を
  伴わない修正）が、回帰テスト3件を実際に同梱していたのに `HARD:fix-without-test` で
  ブロックされた。テスト判別がパス（`TEST_PATH_PATTERNS`）のみで、インライン形式の言語では
  「テスト同梱」を原理的に検出できなかった——テストと生成器をペア修正する間は生成器側の
  パスが偶然一致するため顕在化しない型の穴（採用先で該当22ファイルを確認）。
  誤ブロックの実害は「fix を chore/refactor と名乗って逃げる」誘導＝**接頭辞の意味論
  そのものの侵食**（G10 の対を成立させている前提が壊れる）。
- 実装: `repo_scan.py` に列充填スロット `INLINE_TEST_PATTERNS`（拡張子→追加行パターン）を
  新設し、検査2・検査6 の「テスト同梱」判定を「パス一致 **OR** ステージ済み diff の
  追加行一致」へ拡張（実装は `check_commit_msg.py` の `staged_has_test`——データはスロット・
  実装はスクリプト §7.3）。発火条件も「どちらかのスロットが充填済み」へ拡張し、
  `binding-dead-pattern`（§3.3）の対象表へ同スロットを追加（充填時の拡張子取りこぼしも
  既存の門で検出される）。カタログは rust@5 で充填値
  （`#\[cfg\(test\)\]`・`#\[(\w+::)?test\]`）を、他3列は該当なし判断を版上げで記録。
- 対象外の境界（判断ごと記録）: 検査8（test-shrink）は numstat のファイル単位計数のため
  インライン形式の純減は見えないまま（diff 行の増減では追跡と削除の区別が近似できず
  偽陽性>価値——必要になったら版上げで検討）。red-first（§5）の単独実行対象にも
  ならない（rust 列の「単一テストファイル実行=該当なし」の既存判断のまま）。
- DoD（実測済み——一時 git リポジトリ）: ① インラインテスト追加のみの `fix:` → exit 0
  ② テスト無し `fix:` → `HARD:fix-without-test` で exit 1 ③ パス一致テストの `fix:` →
  exit 0（回帰なし） ④ 両スロット空（キット原本状態）→ 不発 ⑤ `feat:` テスト無し →
  `SOFT:feat-without-test`・インライン同梱で沈黙。

### Phase 43 — v2.41 同梱 ✅（オラクルの種類の契約化——実例より性質・性質より差分）（G10/G9/G7）

- 経緯: 2026-07-14 の外部調査（`surveys/SURVEY_LLM_TESTGEN.md`——Meta TestGen-LLM / ACH /
  Property-Generated Solver）。LLM 生成テストが実装と欠陥を共有する self-deception
  サイクルに対し、制約充足系では実例オラクルより性質形（PBT）が産業・学術の収斂点で
  あることを確認。キットは「テストの存在（fix⇔テスト対）・バグ再現の証明（red-first）」
  は持つが、**オラクルの種類**（何と突き合わせて正誤を判定するか）が無規定だった。
- 実装: §9.6 新設（差分検証>性質形>実例の優先順＋買うもの/買わないものの脅威モデル）・
  `missing-property-test`（soft・§3.3——`SOLVER_DIRECT_CALL_PATTERNS` 充填時のみ発火・
  存在検査のみ）・§9.1 に UNKNOWN 三値契約・§11 Step 0 表B に「独立オラクルの有無」・
  GOALS 運用に「降格の統治」（昇格の非対称閾値の逆方向）・保留2件（製品変異テストへ
  制約1本壊しの領域特化形を追記／UI 第二層の変化検出を新規登録）。カタログは
  python-uv@8（マーカー充填値＋hypothesis 実行済みサンプル）・rust@7（proptest
  マーカー——実地一致は要実測）。
- DoD（実測済み——一時 git リポジトリのフィクスチャ 2026-07-14）: ① solver 充填＋
  マーカー充填＋性質テスト無し → `SOFT:missing-property-test` 1行 ② hypothesis import
  追加 → 沈黙 ③ solver 未充填 → 沈黙（不発） ④ solver 充填＋マーカー未充填 → SOFT
  発火（静かな不発にしない — G9）。キット原本の `check` は従来どおり 5 SOFT・exit 0。
  hypothesis サンプルは 3 性質 pass・違反注入（容量チェック除去）で不変量 fail を実測。

### Phase 44 — v2.42 同梱 ✅（導入 CLI の整備＋管理区画＋live probe——外部ハーネス調査の採用実装）（G12/G13/G2/G9）

- 経緯: 2026-07-14 の外部ハーネス調査（`surveys/SURVEY_HARNESS_TOOLS.md`——oh-my-harness /
  probity / agent-guard / dwarvesf / vibeguard を一次確認）。実施計画は
  `docs/plans/2026-07-14-harness-tools-import.md`。導入・更新の「プロンプト＋エージェントの
  意味解釈」依存を縮小し、機械で決定できる部分を専用 Python へ移した（ユーザー要件）。
- 実装:
  - **`install_kit.py --detect`**: マニフェストから採用列の候補を提示（提示のみ・確定は
    Step 0）。Step 0 の質問は機械で導出できない5項目へ縮小（G12）。
  - **`install_kit.py --diff / --check`**: 適用前プレビュー（±行数つき）と CI 用ドリフト
    検出（全て OK/KEPT/SKIPPED なら exit 0）。いずれも書き込みなし。
  - **管理区画スプライス**: Python 充填先4ファイルに `>>> GUARDRAILS BINDING >>>` 区画を
    導入。UPGRADED は区画の中身だけ既存から引き継ぐ・区画欠落は
    `CONFLICT:unmarked-binding` で停止（充填の黙失防止 — G9）。YAML 系は対象外
    （判断は保留節・調査 §1）。
  - **`dev.py selftest / doctor`**: 門コーパス一括＋環境診断の集約フロント（新検査なし）。
    計画の動詞名 `test` は §12.1 の既存 test（製品テスト）と衝突するため `selftest` に
    訂正（計画からの変更を記録）。
  - **`dev.py probe --live`**: 実ホスト経路の発火確認（nonce 入り sentinel→違反ログ照合の
    2段階）。Step 4 完了条件⑩に追加。
  - **副次修正（DoD 中に発見）**: インストーラのマニフェストがファイルシステム走査のため、
    作業チェックアウトからの直接インストールで gitignore 済みローカルテレメトリ
    （violations.jsonl・session/）が配布物に混入していた——is_meta で明示除外
    （docs/plans/ / surveys/ も同様にキット自身の記録として除外）。
- DoD（実測済み 2026-07-14）: detect=混在リポジトリで2候補＋残余質問一覧・空ディレクトリで
  候補なし明示／diff=書き込みゼロ（49 INSTALLED 表示・ファイル未作成）／check=クリーン
  導入後 0 件 exit 0・改変注入で exit 1／splice=充填のみ差分→OK・区画外改変→UPGRADED で
  充填保持＋区画外更新をバイト確認・マーカー欠落→CONFLICT:unmarked-binding／
  selftest=3チェッカ全緑／doctor=事実8行＋check 連結（binding-drift の hard を実際に
  1件検出——区画コメントの例示が刻印パターンに誤マッチした自己偽陽性を doctor 自身が
  発見し、同コミットで是正）／probe --live=**実セッションで完走**（sentinel が実
  PreToolUse にブロックされ、違反ログの nonce 照合で PASS——シミュレーションではなく
  実ホスト経路の実測）。

### Phase 45 — v2.43 同梱 ✅（門の台帳と `dev.py gates`——「何ができるか」の発見導線）（G4/G9/G2）

- 経緯: 主目的を「確定実行で信頼領域を広げるレール」に再定義した後、「使う人はこのキットが
  何をできるかをどうやって知るか」という導線の穴が残った（v2.21 の CUSTOMIZE.md 導線と
  同型——機構は揃っていても発見の経路が無ければ存在しないのと同じ — G9）。README への
  全機能列挙は §3.3 との二重正本化（ドリフトの温床）のため不可——機械可読の台帳＋実状態
  からの表示＋台帳自体の門、の3点で解く（STRUCTURE.md の「生成＋鮮度検査」と同じ型）。
- 実装: `repo_scan.py` に `GATE_REGISTRY`（約60行の門の台帳: 識別子・区分・有効化条件・
  一行説明）。`dev.py gates`（内蔵動詞）が台帳を**このリポジトリの実状態つき**で表示——
  状態は実物から計算する（バインディング充填の truthiness・settings.json のフック配線）。
  `gates-registry-drift`（§3.3・hard）が台帳と検査器コードの一致を2方向で機械検査する。
  発見の経路: README（主目的と索引）→ `dev.py gates`（実状態つき全機能）→ GUARDRAILS
  各節（契約）→ CUSTOMIZE.md（調整項目）。
- 設計判断: 逆方向照合は「台帳の行そのものが照合対象ソース（repo_scan.py）に含まれる」
  自己循環があり、存在1回では幽霊規則を検出できない——**出現2回以上**（台帳の行＋実装側の
  実体）を要求する形で除去（違反注入で実測した穴）。有効化条件が列充填の規則は
  充填変数の truthiness で「未充填（列充填で有効化）」と表示——不発の規則を有効と偽らない
  （G9。binding-dead-pattern と同じ向きの正直さ）。
- DoD（実測済み 2026-07-14）: ① クリーン状態で check exit 0（台帳と検査器が一致）
  ② 未登録IDの emit を注入 → `HARD:gates-registry-drift`（未登録）1行 ③ 台帳にだけ
  幽霊規則を注入 → 同 hard（幽霊）1行 ④ 除去後 exit 0 ⑤ `dev.py gates` がキット原本で
  §1〜§12 の全区分を表示（フック層=配線済み・列充填系=未充填・常時系=有効）。

### Phase 46 — v2.44 同梱 ✅（導入経路の効率化——easy 版の廃止と existing/update の CLI 前提化）（G13/G12/G2/G9）

- **PROMPT_claude_code_easy.md を削除**。存在理由（検証を削って導入を速くする）が
  二重に消滅した: ① Phase 44/45 で本体経路自体が機械化された（--detect が Step 0 の
  読み取りを、--diff が CONFLICT 往復を、管理区画が充填復元を、gates が状態把握を代替）
  ② 「配線はされているが末端まで実証されていない規則を抱えたまま運用開始」という easy の
  妥協は、主目的（確定実行で信頼領域を確実に増やす——GOALS 存在理由）と正面矛盾する。
  速さは検証を削らず機械化で買う、が本キットの解（判断ごと記録——再提案時はこの節を引く）。
- **PROMPT_claude_code_existing.md の CLI 前提化**: Step -1a を3段（--detect → --diff →
  本実行）に再構成し、フック有効化の実測を手動の `--no-verify` 試行から
  `probe --live`（nonce 照合の機械判定）へ置換。Step -1b の棚卸しは --detect / doctor /
  gates の出力を骨格にし、手読みは機械が出せない部分（レイヤー・エントリポイント）に
  限定。Step 10 の監査は selftest / doctor / gates に統一し、「gates の初期採取との差分＝
  この導入で有効化された門の一覧」を最終報告の形式にした。
- **PROMPT_claude_code_update.md の CLI 前提化**: U0 基準線に gates 全出力を追加。U1 を
  3段（--diff プレビュー → --keep-source 付き本実行 → --check でドリフト0件の確定判定 →
  後片付け実行）に再構成——「更新が完全に届いた」を自己申告にしない。U3 は gates diff を
  第一の機械入力に（散文の §10 を読む前に台帳差分で増分を掴む）、U5 は selftest 一括＋
  フック層更新時の probe --live 再実測。
- DoD: 文書変更のため実測は次の実導入/実更新で行い結果をここへ追記する（Phase 41 と同じ
  整理）。easy への残参照ゼロは grep で確認済み（README_SETUP の「PROMPT 3本」表記は
  4本へ是正）。

### Phase 47 — v2.45 同梱 ✅（充填と規則DoDの機械化——導入から LLM を追い出せる部分を全てコードへ）（G12/G13/G2/G9/G1）

- 経緯: 導入所要（新規=半日級）の支配項は「エージェントの手作業」——カタログからの
  コピペ充填と、規則ごとの手動違反注入だった。どちらも決定的な作業であり LLM の仕事では
  ない。ユーザー指示（LLM 必須の残りを列挙し、それ以外をコード化——環境パターンごとの
  コード肥大は許容）に基づき2本のツールへ移した。分担の正本は §11 冒頭「機械と LLM の
  分担」節。
- 実装:
  - **`scripts/fill_bindings.py`**: カタログの `<!-- FILL <対象> -->` マーカー付き
    paste-block を管理区画へ機械充填＋6ファイルへ刻印。冪等（同一ブロックは SKIPPED）・
    dry-run・複数列の併用可。初回充填専用（版上げ差分の意味マージは U4 の持ち場のまま
    ——判断ごと記録）。カタログ4列に FILL マーカーを付与し、散文だった充填指示を
    fenced 化（ts@10 / python-uv@9 / dart@7 / rust@8）。
  - **`scripts/check_rule_dod.py`＋`tests/injections/python-uv.json`**: 列の違反注入
    コーパス（注入→発火→除去→沈黙）を2回の check 実行に束ねて再生する。`dev.py dod`。
    python-uv は6規則（test-sleep / test-nondeterminism / test-network /
    log-direct-call / deprecated-api / missing-log-coverage=SOFT 側の証明）。
    コーパス未同梱の列は表示つき素通し（DoD 道具であり門ではない）。
  - **刻印を管理区画の内側へ移設**（repo_scan / post_edit 2フック）: 区画外の刻印は
    UPGRADED で消える——DoD 中に binding-drift が実際に検出した（門が門を守った実例）。
- **DoD 中に発見・是正したキット本体のバグ2件**（初の実充填が炙り出した——python-uv 列は
  【要実測】のまま実充填されたことが無かった）: ① `LOG_EXIT_PREFIXES` にフック
  2ディレクトリが無く、python 列充填の瞬間にキット自身のフックの正当な print
  （ハーネス契約）が `log-direct-call` 23件の自己偽陽性になる → 既定除外へ追加
  ② 刻印の区画外消失（上記）。
- DoD（実測済み 2026-07-14・フィクスチャ全経路）: install → fill（4 FILLED＋6 STAMPED・
  再実行で4 SKIPPED=冪等・dry-run 書き込みなし）→ check（HARD は Step 1 前の想定3件
  のみ）→ gates（python 系規則が「有効（充填済み）」表示）→ dod（6/6 PASS・除去後
  沈黙）。列なしのキット原本では dod は表示つき素通し exit 0。
- **追記（同日）——コーパスを全規則へ拡張**: `tests/injections/common.json`（言語なし
  6ケース: env-file-tracked / mcp-not-allowed / context-doc-too-large / dir-too-crowded /
  commit-msg-format / commit-too-large——**キット原本でも dod が意味を持つ**）を新設し、
  python-uv を12ケースへ拡張（file-too-long / test-calls-solver-direct（requires 付き）/
  missing-role-header / commit 段の fix-without-test / feat-without-plan /
  feat-without-test を追加）。ランナー v2: commit 段の再生（check_commit_msg.py の直接
  呼び出し・1ケース隔離・index クリーン前提）・`requires`（充填条件つきケース——未充填は
  SKIP 表示で「不発を PASS と偽らない」G9）・注入先が既存なら SKIP(exists)・多ファイル
  ケース。実測: フィクスチャ 18ケース中 16 PASS＋正当 SKIP 2（solver 未充填時／
  file-too-long はキット自身のスクリプトが 500 行超のため基準線発火＝帰属不能）、solver
  充填後は該当ケースも PASS。キット原本で共通6ケース全 PASS。
  **コーパス対象外の判断（記録）**: ①除去・改変系（missing-required /
  agents-import-missing / governance-without-goal / undeclared-dependency / test-shrink）
  ——ランナーは追加専用（既存ファイルの書換・削除は事故面が大きい。これらはキット原本の
  違反注入 DoD・実運用の発火で実証済み） ②キット自己検査系（binding-* / hooks-* /
  gates-registry-drift / installer-token-drift）——キット原本の Phase DoD の持ち場
  ③列・プロジェクト固有（layer-violation / ui-missing-testid / missing-catch-unwind /
  orphan-file 等）——各列のコーパス整備時に追加（ts/rust/dart は列コーパス未作成）
  ④不在系（missing-property-test / missing-folder-claude-md）——「無いこと」が違反の
  規則は追加注入で再現できない ⑤CI 管轄（red-first / commit-msg-history-mismatch）。
- **追記2（同日・二度手間の是正）**: コーパス導入後も §11 Step 2/4/5・PROMPT 2本に
  手動違反注入の指示が残り、字義通りに読むと dod で済む証明を手で繰り返す構造に
  なっていた（契約と実装の食い違い——§0 の同一コミット原則に照らし遅延是正）。
  Step 2/4/5 と PROMPT の DoD 文言を「コーパス対象は dod・手動は対象外5分類のみ」へ
  統一し、実行規律6に「dod で済む注入を手でやり直さない（逆向きの二度手間）」、
  規律8に「注入の後始末に checkout/restore を使わない（開発中の実測事故から）」を追加。
  規則追加の登録先（最大5箇所）の一覧を §3.3 のレシピに1本化。doctor の check 内包を
  §12.1 に明記（監査での多重実行の削減）。

### Phase 48 — v2.46 同梱 ✅（フックシム改変の迂回封鎖——`pre-commit uninstall` の非語版）（G7/G9/G10）

- 経緯: ユーザーの指摘「pre-commit を抜けるコードが登録されていない気がする」を probe で
  点検し、**シムの直接改変/除去が素通し**だったことを実測。`pre-commit uninstall` は
  ブロック済みだったが、`rm .git/hooks/pre-commit`・`: > .git/hooks/pre-commit`（切り詰め）・
  `chmod -x`・`mv … /tmp`・`ln -sf /dev/null …`・`tee`・`truncate` は「uninstall」の語を
  使わずに同じ全ゲート迂回を達成できた（環境変数・`-c`・`config --add` 経由の hooksPath は
  既に DENY で塞げていたため、穴はこのシム改変系だけ）。
- 実装: `guard_git_bypass.py` に、`.git/hooks/` 配下を変異動詞（rm/mv/chmod/ln/tee/
  truncate）で触る、または切り詰めリダイレクト（`> .git/hooks/…`）で潰す操作の
  セグメント単位ブロックを追加。参照（`cat`/`ls`）と正規の `pre-commit install`
  （語に `.git/hooks/` を含まない）は素通し。`permissions.deny` には足さない——`rm` の
  前方一致は広すぎる（deny=前方一致の第二防壁・主防壁はフック、の既存構造どおり。
  §2 の外部裏書き）。状態側（シム消失後）は従来どおり `hooks-not-installed` /
  `hook-type-missing` が静的検出（操作の防壁と状態の検査で挟む — G7/G9）。
- DoD（実測済み 2026-07-14）: 9経路が DENY（rm・rm -f・: >・echo >・chmod -x・mv・
  ln -sf・tee・truncate、pre-push/commit-msg も）／4正規操作が ALLOW（cat・ls・
  pre-commit install・メッセージ内に `.git/hooks` を含む commit）。guard コーパスへ
  DENY 10行＋ALLOW 2行を追加し**全88行 PASS**（門番の回帰＝改修が過去の塞ぎを開け直さない
  ことの機械保証 — G10）。

### Phase 49 — v2.47 同梱 ✅（Fable更新後の目的監査で見つかった穴の一括是正）（G1/G2/G4/G7/G9/G10/G13）

- `.git/hooks` の表記を `/` へ正規化し、Windowsのバックスラッシュ、引用付きパス、
  PowerShell変更動詞・ネストしたPowerShell/cmd、ディレクトリ自体の移動、重複スラッシュを
  迂回コーパスへ追加（全99行PASS）。
- Codexアダプタの操作直前モードは、不正JSON・Gitルート解決失敗をexit 2へ倒す。Stop/所有権の
  fail-open契約は維持し、モードごとの非対称を回帰検査する。
- `fill_bindings` は全列・全対象を先に検証し、1件でも不正なら書き込み前に終了する。
  `check_fill_bindings.py` が不正先頭列＋有効後続列でも無変更であることを再生する。
- pre-commit/CIへ名前付き管理区画を導入し、4列すべてのYAMLとランタイム動詞を機械充填する。
  4列すべてに違反注入コーパスを同梱し、rule-dodをselftest/pre-commit/CIへ配線した。
- 直接インストールのマニフェストから `.ruff_cache` 等の生成キャッシュを除外し、Windowsの
  Codex検査出力をUTF-8へ統一した。

### Phase 50 — v2.48 同梱 ✅（実行される参照実装——「サンプルは示すが強制しない」の構造化）（G5/G6/G8/G13/G9）

- 3層レール（①レール＝コードの形 ②サンプル＝CI が緑を保証する実行される参照実装
  ③最小限の hard＋理由付き免除の soft）を §9.7 として明文化。hard 検査は増やしていない
  ——第2層は「規定のやり方を一番楽な道にする」レールであり門ではない。
  設計根拠は `docs/plans/2026-07-15-test-log-3layer-rails.md`。
- ログ出口の**契約テスト**を §8.2 に規定し、実行可能サンプル（vitest 2テスト緑を実測）を
  ts-react-web 列 @12 に同梱。§11 Step 7 完了条件③・Step 8b やる/完了条件⑤に組み込み。
- ts-react-web 列の `LOG_BOUNDARY_PATTERNS`（fetch＋catch 節）/`LOG_CALL_PATTERN`（logOp）
  を充填（@8 が残した別件の解消）。§8.4 の被覆検査4ケースDoDを実測し、列DoDコーパスへ
  `missing-log-coverage` を追加（`requires` 付き——未充填では SKIP(unfilled)。
  `fill_bindings ts-react-web@12` 一時適用で15ケース DOD:PASS を実測）。
  rust / dart-flutter の同充填は引き続き別件（値ごとに実測——G13）。

### 保留（トリガー待ち。トリガー成立まで実装しない——ここが登録先）
- **workflow 自己改変の防御（規定＋検証）**（G7——v2.36 登録）: §2e の残余経路②。
  required checks は PR ブランチ側の workflow 定義で走るため、`guardrails-ci.yml` を
  骨抜きにした PR は required を通過し得る——Step 9 ④ の検証（§3.5）が確かめるのは
  「登録の有無」であって workflow 内容の保護ではない（外部レビューの指摘どおり別のルール）。
  塞ぐ実装は規定可能で機械検証も可能: `CODEOWNERS` で `.github/` を人間オーナーへ割当＋
  ブランチ保護/rulesets の `require_code_owner_reviews`（既存の gh api 照会と同系統で検証
  できる）、または push ruleset の file path 制限。トリガー = 採用先が**エージェントに
  main への merge 権限を与える運用**を採る時（人間が全 PR の diff をレビューする運用では
  `.github/` の改変はレビューが見る前提で、追加設定は摩擦だけ増える——§2e の分担どおり）。
  判定時の制約も記録しておく: CODEOWNERS の強制は私有リポジトリでは有償プラン限定。
- **免除・接頭辞の監査指標**（G4——v2.35 登録）: レビュー規約に割り当て済みの乱用点検
  （`RED-FIRST-EXEMPT:` / `NO-LOG:` / `NONDETERMINISM-EXEMPT:` の頻度・fix を refactor/chore
  と名乗る接頭辞回避）は現状**測る手段が無い**——git 履歴 grep＋違反ログ（§3.6）から
  免除率と接頭辞分布の推移を出す読み取り専用スクリプト1本で計測可能になる。
  トリガー = 採用先で乱用点検が実際に回らない・判断に迷う実測が出た時、**または**
  違反ログ運用で soft→hard 昇格判断が最初に発生した時（同じ集計の別断面）。
  実装形 = 集計と表示のみ（閾値判定・自動昇格はしない——解釈層を門に入れない §3.6）。
- **効果の評価設計**（G11/G4——v2.35 登録）: README「効果は未実測」の解消条件をここに固定
  する。個々の門の違反注入 DoD は全て実測済みだが、「出戻り・バグが減る」という製品価値
  そのものは未測定——キット自身の認識論（完了=実行結果）に照らした最大の未解決事項。
  トリガー = **最初の実採用プロジェクト**。測るもの（いずれも既存の機械記録から取れる形に
  限定する）: hard 違反率・soft 無視率の推移（違反ログ §3.6）・免除率（上の指標と共通）・
  fix の再発率（同一箇所への fix 再訪—— git 履歴）・CI 所要時間。before/after 比較は
  導入前履歴のあるリポジトリ（PROMPT_claude_code_existing 経路）でのみ成立する——
  新規リポジトリでは推移の観測のみと明記しておく（誇張しない——README の立場を維持）。
- **Chrome DevTools MCP（タスク単位・常駐しない）**（G4）: トリガー = Web 列の採用先で
  **性能調査**（Web Vitals・performance trace・ネットワーク詳細）が実タスクとして発生した時。
  運用形 = `claude mcp add chrome-devtools npx chrome-devtools-mcp@latest` → 調査 →
  remove。**`.mcp.json`（常駐枠）には入れない**——操作系は Playwright と同等（両者
  a11y ツリー）で独自価値は性能分析のみ、が 2026-07-07 調査の判定。
- **Context7 MCP**（G4/G13）: トリガー = `deprecated-api` の検出やレビューで**同一
  ライブラリの旧作法生成が繰り返し実測**された時（門で止まってはいるが再発が続く＝
  供給側の欠乏）。採用時は採用規律ゲート3条を通し `MCP_ALLOWED_SERVERS` へ追加＋列の
  `.mcp.json` へ2ツールのみ。呼ぶかは心得依存という弱さを判定に明記すること。
- **Serena MCP（大規模既存リポジトリ限定の再評価）**（G3）: トリガー =
  PROMPT_claude_code_existing の導入先で、清掃 Phase 中の参照追跡がネイティブ検索で
  **溢れる実測**（コンテキスト超過・誤編集）が出た時。導入条件 = `.serena/memories/` は
  生成させないか .gitignore（§13 中央メモ禁止の維持）・編集系ツール不使用（編集は門の
  内側で）。新規リポジトリでは不採用が既定（索引=STRUCTURE.md＋500行/7ファイル上限で
  役割充足・効果の実測が割れている——2026-07-07 調査）。
- **Skills 化（AGENTS.md の手順章の分割）**（G3）: トリガー = `/context` の実測で
  AGENTS.md＋フォルダ CLAUDE.md の常駐が問題化した時、**かつ** `.agents/skills`
  相互運用標準の成熟を確認した時（Claude Code 固有層を厚くする採用は v2.10 の
  多エージェント方針と逆行するコストがある——Phase 22 の境界）。
  センサー = soft `context-doc-too-large`（v2.17——警告の常態化がトリガー実測に当たる）。
- **合流の門（GitHub Merge Queue——調査⑤・企業実証: Rust bors / Uber SubmitQueue /
  Shopify）**（G1/G9）: トリガー = **並行 PR の常態化**（複数エージェント並走・共同開発化）
  **または合流起因の main 赤を1回でも実測**した時。守る対象 = マージスキュー（個別に緑の
  PR 同士の意味的衝突）——**PR 単位の CI では原理的に守れず、リポジトリ内ファイルでも
  実装できない層**（ホスティング側の直列化が正本）。発火時の実装は設定のみ: Step 9 ④の
  required checks を前提に Merge Queue を有効化。現行の部分防御 = CI の `push: main`
  再実行（壊れたら即検知——予防はしない、を明示して運用）。単独・低並行では待ち時間
  コスト > 価値のため発火まで有効化しない。自作（bors 自前運用）は不採用（標準機能が
  存在する今、重複排除ゲート違反）。
- **UI 第二層の回帰固定（visual regression ＋ smoke E2E）**（G6/G13——v2.41 登録・
  SURVEY_LLM_TESTGEN.md §3）: UI は二層に割れる——**ロジック層**（正解あり。クォータ計算・
  状態遷移・権限判定を純関数に引き剥がし、既存管轄 `layer-violation`・`ui-missing-testid`・
  薄皮UI（G6）で守る）と**プレゼンテーション層**（正解なし。「正しい見た目」を定義する
  不変量が書けず、**門の原理的対象外**——§9.6 のソフト制約と同じ理由）。後者に使える機械は
  検証でなく**変化検出**のみ: ①スクリーンショット差分（人間が一度承認した見た目からの
  差分だけを検出——Playwright `toHaveScreenshot` 等） ②主要導線の smoke E2E（「ボタンが
  画面外」「主要導線でエラー」という**崩壊の下限**だけ測る——自然さの上限は測らない）。
  いずれも列の paste-block 候補。トリガー = UI 比重の高い採用先で**見た目起因の出戻りを
  実測**した時（スクリーンショット差分はレンダリング環境依存の偽陽性——フォント・
  アンチエイリアス・OS 差——が知られており、実測前の導入は摩擦だけ増やす。導入時は
  CI 環境固定＋しきい値つき比較で開始）。自然さ・美しさの上限は人間の目視が正本——
  高速目視ループ（§12.1 `up`＋hot reload）がそれを支える既存機構。
- **PostToolUse 秘密マスク**（agent-guard 型——SURVEY_HARNESS_TOOLS.md §2）（G7/G9——
  v2.42 登録）: ツール出力に混入した秘密値をモデル到達前に置換する。実現可能性は
  **確定済み**（`hookSpecificOutput.updatedToolOutput` — HARNESS-VERIFIED:
  code.claude.com/docs/en/hooks 2026-07-14。公式が redaction 用途を明記）。即採用しない
  理由 = 常駐予算（全ツール呼び出しに毎回フック1本——G11/G3）と偽陽性（正当な出力の
  破壊）。トリガー = 対象リポジトリが**本番運用・顧客データ段階**に入った時（依存・
  脆弱性監査と同じ閾値）、または**ツール出力経由の秘匿値混入を1回実測**した時。
  設計制約を先に記録: Codex には同等フィールドが無い（agent-guard も additionalContext
  代替）＝マスクは Claude Code 限定の門になる。
- **requireCommand 型の順序ゲート**（probity 型——「A 実行済みでなければ B を禁止」）
  （G7——v2.42 登録）: 例 = deploy 前に check・migration 前に backup。トリガー =
  採用先で**順序起因の事故を実測**した時。実装形 = セッション状態
  （`.claude/session/`——Phase 16 基盤）＋PreToolUse。§12.1 の共通動詞と相性が良い
  （動詞の実行記録をセッション状態に落とせば判定はファイル存在検査で済む）。
- **Clean Room 隔離テスト**（Builder から読めない受け入れテスト——調査④）（G7）:
  トリガー = **テストの改変・弱体化による門の欺きを実際に観測した時**（センサー =
  `test-shrink` の警告常態化）。設計スケッチ: `.cleanroom/` ＋ `.claude/settings.json` の
  `permissions.deny: Read(.cleanroom/**)` ＋ CI 専用実行。コスト注記: 隠しテストは
  **人間が書く**しかない（LLM は読めない物を保守できない）——単独開発では高価なため
  発火まで実装しない。
- **依存・脆弱性監査の CI ジョブ**（osv-scanner / cargo audit / npm audit 等）（G9）:
  トリガー = 対象リポジトリが**本番運用・顧客データ段階**に入った時。設計上の緊張を
  先に記録（調査③）: アドバイザリ DB は日々更新され**同一コミットの CI 結果が時間で
  変わる**（G1 決定性と衝突）——ゆえに非ブロッキングの警告ジョブで開始し、運用実測後に
  ブロッキング昇格を判定する。列の paste-block として追加（キット共通ジョブにはしない）。
- **ストリークブレーカー**（G7）: 同一ファイル連続編集 N 回で強制停止（スラッシングの
  機械的切断——AGENTS.md テンプレ §10-4「2回連続で落ちたら原因調査」の編集側の対）。
  トリガー = Phase 16 のセッション状態基盤（`.claude/session/`）導入後、実セッションで
  スラッシングが観測された時（PreToolUse でのカウントは基盤の副産物として安価）。
- **製品テストへの変異テスト**（G10・mutmut / Stryker 系）: 門への変異テスト
  （違反注入・Phase 9 コーパス）は実施済み。製品側は red-first（Phase 18）が先。
  トリガー = red-first の required 運用（Phase 21・v2.9〜）が安定し、CI 予算に余裕が出た時
  （導入時もカバレッジ前例に従い「表示のみ→ラチェット」）。
  **領域特化形（v2.41 追記——SURVEY_LLM_TESTGEN.md）**: 制約充足系（表Bで確率的
  コンポーネント有）では、汎用 mutant（演算子置換）より**「制約を1本壊した定式化」**が
  変異体の自然な単位——性質テスト群（§9.6）がそれを赤にできるかで、性質自体の検出力を
  測る（Meta ACH の mutation-guided 方式の領域版。`missing-property-test` が存在までしか
  見ない「質」の穴を、発火時にこれが埋める）。トリガーは従来のまま。

## 11. 新規リポジトリのブートストラップ（言語・構成を指定されたら本節だけで全機構を移植する）

### 機械と LLM の分担（v2.45・Phase 47——導入の決定的な部分は全てコードが担う）

**機械（決定的・LLM の仕事ではない）**——専用 CLI の実行順:
`install_kit.py --detect`（列候補）→ `--diff` / 本実行（配置・マージ判定）→
`fill_bindings.py <列ID@版>`（paste-block の管理区画への充填＋刻印——コピペの機械化）→
`check_structure` / `gates`（充填の検証と状態表示）→ `dev.py dod`（列コーパスの
違反注入→発火→除去→沈黙の機械証明）→ `dev.py selftest` / `doctor`（門と環境の監査）→
`install_kit.py --check`（以後の版追随の CI 判定）。

**LLM / 人間にしか出来ない残り（これだけがプロンプトの仕事）**:
1. **表B/D の設計判断**: レイヤー構造と依存方向・ログ出口の置き場所・確率的コンポーネント
   と独立オラクルの有無・中核不変条件とその強制層（機械は事実を提示できるが、何が
   致命かは業務判断）。
2. **文書の散文**: AGENTS.md / CLAUDE.md の ★ のうちプロジェクト固有の記述
   （何のアプリか・固有名詞・領域知識）。
3. **既存リポジトリの解釈と清掃**: 赤テストの方針・大規模是正の扱い・既存設定（YAML 系）
   との意味的統合・清掃 Phase の実施（print 移行・レイヤー是正はコードの書き換え）。
4. **新しい列を起こす**: カタログに無い言語のバインディング設計（起こした列は還元され、
   2回目からは機械側へ移る——G13）。
5. **参照実装の適合**: ログ出口サンプル・ソルバーラッパーを実プロジェクトの型に合わせる部分。
6. **セッション内操作と可否判断**: `/hooks` の承認・`probe --live` の sentinel 実行・
   CI への実 push の可否（Step 9）。
7. **想定外の診断**: CLI が exit 2 / 想定外の CONFLICT を返した時の原因調査。

この分担の含意: 列とコーパスが揃った言語では、導入の時間は「機械の数分＋LLM の残り
1〜7」まで縮む。列の paste-block・違反注入コーパスを充実させることが、そのまま導入の
機械化率を上げる（コードは肥大するが、決定的なコードの肥大は負債ではなく資産——
検査と同じ側に積まれる）。

**発動条件**: 本書を渡された LLM が「言語は◯◯、構成は◯◯で新規リポジトリを作って」と
指定されたら、追加の指示を待たずに Step 0 → 10 を**この順で**実行する。
**§10 冒頭の実行規律をそのまま適用**（順序固定・1 Step = 1 コミット・違反注入必須・
虚偽 ✅ 禁止・途中でターンを終えない）。

**配置の前段**: キットがまだ zip / 展開フォルダのままルートに置かれている場合、手で
コピーせず `scripts/install_kit.py` で配置する（README_SETUP.md §1 が正本。既存ファイルは決して
黙って上書きせず、衝突は CONFLICT 行で停止・キット系統の版上げは git 履歴を安全網に
UPGRADED・成功時は zip と展開元を自動で後片付け——G2/G9）。

設計方針: 本書の §1〜§9・§12 は「機構の契約」、**穴埋めの正本は `bindings/catalog.md` の
検証済み列**（本節の表A/B/Dはそのスキーマ定義）。移植とは契約を変えずに列を選んで
充填することであり、**契約側を新言語の都合で緩めない**（緩める必要が出たら、それだけが
ユーザーへの確認事項）。検証済み列が既にある言語なら Step 0 は「列の選択」に縮退する
（G13: 移植の定数時間）。新言語なら列を1回起こしてカタログへ還元する。

### Step チェックリスト（進捗の正本は `.guardrails/BOOTSTRAP.md` — §3.5・v2.12）
**進捗状態は `.guardrails/BOOTSTRAP.md`（台帳）が唯一の正本**——`check-bootstrap` が ✅ の主張を
再実行検証し、順序・1コミット1Step・虚偽✅を機械強制する（実行規律1〜4の門 — §3.5）。
台帳の更新規律: ✅ 化はその Step の実装と**同一コミット**（台帳を staged に含めることで
監査器が発火する）・完了後も削除しない。下表は各 Step の「完了の証拠」（DoD の要約——
✅ にする前にコミットまでに実測するもの。**監査器が再検証するのはこの一部**であり、
残りは実行規律3が心得として効く）:

| Step | 内容 | 完了の証拠（コミットまでに実測するもの） |
|---|---|---|
| 0 | 入力確定（バインディング表A/B・固有名詞リストC→台帳へ記入） | 全セル充填・空欄ゼロ |
| 1 | 骨格・AGENTS.md / CLAUDE.md・.guardrails/GUARDRAILS.md | 固有名詞とTODOの grep 0件 |
| 2 | uv・`.python-version`・scripts（dev.py 含む）・STRUCTURE.md | 決定性2回一致＋全hard規則の違反注入 |
| 3 | pre-commit 導入（衛生・gitleaks・鮮度・構造） | 3種の違反コミットが各理由で落ちる |
| 4 | 迂回防止（deny・guard・整形・Stopゲート） | `--no-verify`・`--force` push ブロック実測＋コーパス再生 PASS＋Stop 差し戻し実測 |
| 5 | commit-msg 検査 | テスト無し fix が落ちる |
| 6 | push 段（テスト・静的解析・lint昇格） | warning 注入で push が落ちる |
| 7 | ログ単一出口＋hard 検査 | 直呼び注入が落ちる |
| 8 | テスト決定性の hard 検査（＋確率的コンポーネントのラッパー） | 非決定パターン注入が落ちる |
| 8b | ランタイムレール（§12: 動詞充填・決定性供給・操作/観察・E2E） | reset→同一操作2回一致＋testid/network 注入が落ちる＋E2E破壊PRが赤 |
| 9 | CI（全再実行＋テスト＋ツールチェーン固定） | Web 編集の違反 PR が赤 |
| 10 | 総合セルフ監査・残項目の §10 登録 | 監査コマンド群すべて通過＋台帳が全行 ✅/— |

### Step 0 — 入力の確定（ここで埋まらないものだけがユーザーへの質問）
**最初に `uv run --no-project python scripts/install_kit.py --detect` を実行する**
（v2.42・Phase 44——マニフェストから採用列の候補と「機械で導出できない残りの質問」の
一覧が出る。候補はあくまで提示——確定は本 Step — G12）。次に **`bindings/catalog.md` を
開き、採用する列を決める**（複数可。プライマリ列を
1つ選び、対象ファイルへ `BINDING-SOURCE: 列ID@版` を刻印する——§12.7）。**充填と刻印は
手で貼らず `uv run scripts/fill_bindings.py <列ID@版>` が行う**（FILL マーカー付き
paste-block を通常/名前付き管理区画へ機械適用——Phase 47/49。pre-commit・CIも含む）。充填後は
`uv run scripts/dev.py dod` で列の違反注入コーパスを再生し、規則の発火を機械証明する
（同梱4列はすべてコーパス有り。新規列はコーパス追加を列のDoDに含める）。検証済み列が
あれば A の大半は「列の値を貼る」で終わる。新言語なら、以下の A・B・C・D を**全セル
埋めて新しい列としてカタログへ還元する**。「該当なし」と書くのは可、**空欄は不可**。
埋められないセルはこの時点でまとめてユーザーに確認する——**以降の Step でユーザーに
聞くことは無い**設計。

**A. 言語バインディング表**（言語ごとに1列作る）:

| 項目 | 埋めるもの（例は Dart / Rust / Python） |
|---|---|
| 整形（冪等コマンド） | `dart format` / `cargo fmt` / `uvx ruff format` |
| 編集直後 lint（単一ファイル・3秒予算 — §1 第2段） | `uvx ruff check <file>` / `npx --no-install eslint --max-warnings=0 <file>`。予算に収まらない言語は「該当なし（push 段で回収）」と**判断ごと**記録（v2.5） |
| 静的解析コマンド | `flutter analyze --fatal-infos` / `cargo clippy -- -D warnings` / `uvx ruff check` |
| lint 昇格の設定ファイルと対象規則 | print系・空catch系を error/deny に（§8.1 相当） |
| テストコマンド | `flutter test` / `cargo test` / `uv run pytest` |
| print系直呼びパターン | `debugPrint(` `print(` / `println!` `dbg!` / `print(` |
| ログ単一出口の置き場所とタグ名 | §8.2 相当の1ファイル |
| 公開シンボル抽出の正規表現 | §7.4 の流儀（インデント0・公開のみ・近似は仕様） |
| import/参照抽出の正規表現 | レイヤー検査・孤立検出用 |
| テスト内の非決定パターン | sleep系・now系・seed なし乱数（§9.2 相当） |
| テストファイルの判別規則 | パスか命名規則（§3.4 検査2用） |
| 単一テストファイル実行（§5 red-first用） | `uv run pytest <file>` / `npx vitest run <file>`。実行位置が下層なら cwd も記録（`SINGLE_TEST_CWD`）。単独実行が構造的に不能な言語は「該当なし＋代替」を**判断ごと**記録（v2.7） |
| 依存マニフェスト（§3.4 検査4用） | 既定4種（package.json / pyproject.toml / Cargo.toml / pubspec.yaml）は `repo_scan.py` に同梱済み＝**確認のみ**。独自エコシステムなら `DEPENDENCY_MANIFESTS` へ加算追記（v2.5） |
| 非推奨・世代交代パターン（§3.3 deprecated-api用） | LLM が書きがちな旧 API（例: `datetime.utcnow(`）。**出典①②のみ初期値**（規律はカタログ注記）。無ければ「該当なし」を判断ごと記録（v2.6） |
| 設計根拠の対象レイヤー（§3.4 検査5用） | feat⇔plan 対（hard — G14）が新規ディレクトリを監視するルート（例: `src`——`PLAN_LAYER_ROOTS`。v2.6 soft・v2.8 hard） |
| 生成物パターン（手編集禁止・deny 対象） | §2・§7.4 の除外リスト用 |
| ファイル先頭ヘッダーの書式 | `// x — 役割` 相当 |

**B. 構成バインディング**: レイヤー一覧と依存方向（一方向のみ。§5 相当の図を描く）／
必須ディレクトリ・必須ファイル／フォルダ内ファイル数の例外フォルダ／
**確率的コンポーネントの有無**（ソルバー・乱数探索・外部LLM呼び出し等。有なら
Step 8 でラッパー必須）／**独立オラクルの有無**（v2.41——確率的コンポーネント有の場合の
追問。同じ問いに答える第二の実装・仕様検証器・参照実装があるか。例: CP-SAT ソルバーと
独立チェッカー関数。有なら §9.6 の差分検証を Step 8 で配線、無ければ「性質形テスト
（§9.6）が到達可能な上限」と判断ごと記録する）。

**C. 固有名詞リスト**: 雛形（本書と CLAUDE.md）に残る移植元固有の語を列挙する
（この構成なら例: OR-Tools・flutter_rust_bridge・cxx・シフト・solve_for_test 等）。
Step 1 と Step 10 の grep 検査の入力になる。

**D. ランタイムバインディング表**（§12 の穴埋め。カタログの「ランタイム」区分に対応）:

| 項目 | 埋めるもの |
|---|---|
| 共通動詞の配線 | `up` / `reset` / `seed` / `time` / `test` / `e2e` / `fmt` / `check` / `db` の実コマンド（§12.1。「該当なし」の判断込み） |
| ランタイム到達経路（操作レール） | 実UIをエージェントが操作する手段（Web=Playwright MCP／CLI=そのまま実行 等 — §12.4） |
| 観察レール | コンソール・ネットワーク・DB・ログの読み方（§12.3） |
| 中核不変条件 | このアプリで壊れたら致命の性質（例: 打刻テーブルは append-only）と、それを強制する層（DB権限/型/検査のどれ — §12.6） |
| 外部I/Oの列挙 | 依存する外部サービス全部と、そのシームの置き場所・テスト用フェイク（§9.5） |

- 完了条件: A・B・C・D に空欄が無い。採用列と版が決まり刻印済み。この表自体を最初の
  コミットとして記録する（正本3文書を含むコミットは G引用が必須 — §3.4 検査3。
  例: `feat: Step 0 採用列の確定と刻印（G13）`）。
- ありがちなサボり（禁止）: 例の値をコピペして「埋めた」ことにする（**検証済み列からの
  コピペは逆に正**——検証されていない例のコピペが禁止）／正規表現を「実装時に考える」で
  空ける／確率的コンポーネントを「たぶん無し」で流す／中核不変条件を「特になし」で流す
  （データを持つアプリに不変条件が無いことはまず無い）。

### Step 1 — 骨格と文書
- 作る: B に従うディレクトリ骨格／ルート `AGENTS.md`（`AGENTS.md.template` から）——
  **移植元と同一の章構成（§0〜§13 相当）を維持**し、言語固有部だけ A・B の値で置換する。
  章の削除・統合は禁止（章立て自体が本書 §6 などからの参照点）／ルート `CLAUDE.md`
  （`CLAUDE.md.template` から——冒頭 `@AGENTS.md`＋Claude Code 固有節のみ。**同一コミット**。
  規約本文を複製しない — §6）／`.guardrails/GUARDRAILS.md`・`.guardrails/GOALS.md`・`bindings/catalog.md`——
  3つとも複製する（`missing-required` の対象）。契約は言語なしのまま置換不要で、
  各 BINDING 領域へ採用列の paste-block を充填し、§10 の状態表を空で初期化、
  本 Step チェックリストを 🚧 で複製／最小の README。
- 完了条件: ① AGENTS.md に全章が存在し、CLAUDE.md 冒頭に `@AGENTS.md` がある
  （`agents-import-missing` の沈黙で機械確認） ② C のリストで `git grep` して残置 0件
  ③ 各文書に `TODO` が 0件。
- ありがちなサボり（禁止）: 「この言語では不要」と章を省く／固有名詞の除去を目視で
  済ませる（必ず grep で機械確認）。

### Step 2 — uv とスクリプト（§7 の具体化——索引の決定性）
- 作る: `.python-version`／`scripts/repo_scan.py`・`scripts/generate_structure.py`・
  `scripts/check_structure.py`・`scripts/dev.py`（動詞ルーター——この時点では `check` の
  配線と動詞一覧の表示が動けばよく、残りの充填は Step 8b）。**§7.1〜§7.7 の全箇条を
  満たす**（uv run 必須・Windows 絶対規則・共通モジュール・O(N²) 禁止・原子的書き込み・
  決定性・規則ID出力）。シンボル/import の正規表現は採用列の値を使う。初回の
  `STRUCTURE.md` を生成する。
- 完了条件: ① `uv run scripts/generate_structure.py` を2回連続実行して差分ゼロ
  ② `--check` の exit 0/1・内部エラーの exit 2 を実測 ③ **この時点で実装した hard 規則
  すべて**への違反注入——**コーパス対象の規則は `uv run scripts/dev.py dod` の一括再生が
  証明する**（注入→発火→除去→沈黙・PASS 一覧が実績 — Phase 47）。手動注入は
  コーパス対象外（Phase 47 追記の5分類——除去改変系・列固有等）の有効化規則だけ
  ④ 全走査2秒以内。
- ありがちなサボり（禁止）: 1言語分だけ実装して「他も同様」／手動が残る規則の注入を
  代表1件で済ませる（**規則ID × 言語の全組み合わせ**）／A の正規表現を実ファイルで
  試さない／**dod で済む注入を手でやり直す**（実行規律6——逆向きの二度手間）。

### Step 3 — pre-commit 導入（**ここから先の全コミットがゲート下に入る**）
- 変える: `.pre-commit-config.yaml`（衛生一式・gitleaks・generate-structure・
  check-structure。entry は §7.6 のとおり `uv run …`）。
  `uv tool install pre-commit` → `pre-commit install`。
- 完了条件: ① わざと違反（末尾空白＋hard 違反1件＋ダミー秘密）を仕込んだコミットが
  **3種それぞれの理由で**落ちる ② 解消後に同じコミットが通る。以降の Step のコミットは
  すべてこのゲートを通過して積まれる——これが Step の順序を入れ替えてはいけない理由。
- ありがちなサボり（禁止）: config を書いて `install` を忘れる（**fail-open の典型**。
  発火の実測まで含めて完了）。

### Step 4 — 迂回防止
- 作る: `.claude/settings.json`（`permissions.deny`: `--no-verify` / `--force` push /
  `pre-commit uninstall` / `STRUCTURE.md` と A の生成物への Edit/Write）・
  `.claude/hooks/guard_git_bypass.py`（exit 2・fail-closed。--no-verify/-n・SKIP=・
  --force/-f push・core.hooksPath を検出——§2）・
  `.claude/hooks/post_edit_format.py`（A の整形コマンドで対象拡張子を判定——§1。v2.24でPython化）・
  `.claude/hooks/post_edit_lint.py`（A の「編集直後 lint」を充填——§1 第2段。v2.5・v2.24でPython化。
  settings.json の PostToolUse は整形→lint の**直列1コマンド**として同梱済み——並べ替えない）。
  同梱済み（v2.4）: `tests/guard_corpus.tsv`＋`scripts/check_guard_corpus.py`
  （門番の回帰テスト＋probe——§2。v2.5 で前提列 dirty/clean と作業消失ガードの行を追加）・
  `.claude/hooks/stop_incomplete_guard.py`（ターン終了ゲート——§2b。v2.24でPython化）。
  同梱済み（v2.6）: `.claude/hooks/session_baseline.py`＋`guard_human_wip.py`
  （所有権ガード——§2c。settings.json の SessionStart / PreToolUse(Edit|Write|MultiEdit)
  も配線済み）——これらの実体は DoD 実測。
- 完了条件: ① `git commit --no-verify` と `git push --force`（引数順を変えた
  `git push origin -f` も）の実行がブロックされる（実測）
  ② `STRUCTURE.md` への Edit が拒否される ③ 対象ファイルを編集した直後に整形が
  当たっている（差分で確認） ④ `uv run scripts/check_guard_corpus.py` が全行 PASS し、
  guard の規則1つを無効化する注入で赤くなる（§2） ⑤ `uv run scripts/dev.py probe
  "git push -f"` が DENY を返す ⑥ ダーティツリーでの Stop が差し戻され（条件A・exit 2）、
  クリーンでも check の HARD 違反を注入した状態で差し戻され（条件B・exit 2＋規則ID
  入り文面 — v2.9）、フック内部エラー・check 内部エラー（exit 2）注入では**通る**
  （exit 0——§2b の fail-open は §2 と逆向きの注入）
  ⑦ lint 違反を注入した編集で exit 2＋stderr が届き、クリーンな再編集では沈黙、
  整形＋lint 合計が3秒以内（§1・§7.7——v2.5） ⑧ dirty ツリーで `git reset --hard` が
  ブロックされ、clean では素通し・`rm -rf .git` は常時ブロック（§2 作業消失ガード——v2.5）
  ⑨ セッション開始時点で dirty だったファイルへの Edit がブロックされ、commit / stash 後は
  通る（自動解除）・baseline 不在は警告付き素通し・**内部エラー注入（git 不在）でも通る**
  ⑩ `uv run scripts/dev.py probe --live` の2段階（発行→エージェントのセッション内で
  sentinel 実行→PASS）が完走する（実ホスト経路の発火確認——§12.1・Phase 44。Codex でも
  作業する構成なら Codex セッションでも1回実測する）。
  ④の再生（guard コーパス）と所有権ガード・Codex フックの回帰は
  `uv run scripts/dev.py selftest` が一括実行する——個別コマンドを繰り返さない（v2.45）。
  （§2c 所有権ガード——v2.6。fail-open は §2 と逆向きの注入——§2b と同様飛ばさない）。
- ありがちなサボり（禁止）: フック内の想定外エラーを exit 1 で返す実装
  （素通りする——§2 の fail-open）。§2b 側を fail-closed で書く実装も同罪
  （壊れたフックがセッションを終了不能にする——非対称の正本は §2b）。

### Step 5 — commit-msg 検査
- スクリプト（`scripts/check_commit_msg.py`）・フック定義・`default_install_hook_types` は
  v2キットに同梱済み——本 Step の実体は **`pre-commit install` の再実行**と DoD 実測。
  テスト判別は A の規則を使う（§3.4）。
- **発火側（落ちること）は `dev.py dod` の commit 段ケースが一括で証明する**（format /
  fix⇔テスト / feat⇔plan / feat⇔テスト / commit-too-large — Phase 47。①②⑥の
  「落ちる」半分と共通コーパス分）。手動で残るのは**通る側**（テストを足すと通る・plan を
  足すと通る・refactor: を名乗ると通る・Merge 素通し・依存宣言で通る——「解消して通る」は
  コーパス化していない）と④の再インストール実測・⑤の依存検査（改変系のため対象外）。
- 完了条件: ① 不正プレフィックスで落ちる ② テスト無し `fix:` で落ち、A の判別規則に
  合う変更を足すと通る ③ `Merge` 素通し ④ 再インストール後に発火することを実測
  ⑤ 依存マニフェストに1つ追加＋本文言及なしで落ち、`依存追加: <名前> — 理由1行` を
  書くと通る・lockfile のみ／版更新のみは素通し（§3.4 検査4——v2.5）
  ⑥ `PLAN_LAYER_ROOTS` 充填後、レイヤー直下に新規ディレクトリを作る `feat:`（plan 差分
  なし）が `HARD:feat-without-plan` で**落ち**、plan 差分を足すと通り、refactor: を
  名乗っても通る（§3.4 検査5——v2.8 で hard・G14。逃げ道の意味論の実測まで含めて完了）。
- ありがちなサボり（禁止）: install 再実行忘れ（静かに無効——§0 の注意そのもの）。

### Step 6 — push 段と lint 昇格
- 変える: pre-push フック（A のテストコマンド・静的解析コマンド。codegen を持つ構成なら
  鮮度フックも——§4）／lint 昇格の設定（A の設定ファイル——§8.1 相当）。
- 完了条件: ① print 残し等の warning 級違反を注入 → push が落ちる ② テストを1本
  わざと壊す → push が落ちる ③ 除去して push が通る。
- ありがちなサボり（禁止）: 「テストがまだ無い」を理由に push フックを後回しにする
  ——通るテストを1本置いてでも**ゲートを先に立てる**（コードよりゲートが先）。

### Step 7 — ログ単一出口
- §8.2 の具体化: A の「単一出口の置き場所」にログ関数を実装し、`check_structure.py` に
  `log-direct-call`（境界検査を持つ言語なら `missing-catch-unwind` 相当も）を追加。
- 完了条件: ① 出口以外での print 系直呼びを注入 → hard で落ちる ② 実ログが
  `[タグ] 操作名: 詳細 (+Xms)` 形式で出ることを確認 ③ 出口の**契約テスト**（形式を
  固定するテスト——§8.2・v2.48）を同梱し、テストスイートで緑を確認。
- ありがちなサボり（禁止）: 検査だけ足して既存コードの直呼びを移行しない
  （違反ゼロの状態で初めて完了）。

### Step 8 — テスト決定性
- §9 の具体化: A の非決定パターンを `test-nondeterminism` として追加。B で確率的
  コンポーネント「有」なら `xxx_for_test(seed, timeout)` ラッパー＋直呼び禁止 hard を
  実装（§9.1 相当）。
- 完了条件: ① 各パターンの違反注入で落ちる ②（該当時）同一 seed 2回で結果一致・
  timeout を極端に短くしてもハングしない。
- ありがちなサボり（禁止）: 「今のテストには無いから」でパターン追加を省く
  （温床の禁止は予防であって対処ではない）。

### Step 8b — ランタイムレール（§12 の具体化。8 と 9 の番号参照を壊さないため枝番）
- やる: D 表のとおり `scripts/dev.py` の COMMANDS を充填（「該当なし」もカタログに記録）／
  時刻注入シームと `reset`（seed込み）の実装（§12.2）／操作レールの導入（Web 列なら
  `.mcp.json` に Playwright MCP——§12.4）／`test-network`・`ui-missing-testid` の
  パターン有効化／E2E を最低1本（正常系の貫通）と CI の e2e ジョブ（§5）／
  **参照実装1機能**（注入シーム・固定時計・testid・境界のログ記録を実演する雛形＋テスト
  ——§9.7 第2層）を置き、AGENTS/CLAUDE.md から「新機能はこれを雛形にする」と参照する。
- 完了条件: ① `reset` → 同一操作2回 → 状態一致の実測（G1）② エージェントが操作レールで
  UI を1回操作し、観察レール（コンソール/DB）で結果を読めた実測 ③ `test-network`・
  `ui-missing-testid` の違反注入がそれぞれ規則ID付きで落ちる ④ E2E を1本わざと壊すと
  `dev.py e2e` が赤 → 直すと緑 ⑤ 参照実装のテストが通常のテストスイート（＝CI）に
  含まれて緑（腐らないサンプルの成立条件——§9.7）。
- ありがちなサボり（禁止）: 動詞を「あとで配線」で残す（未配線はエラーになる設計だが、
  エラーのまま放置するのは fail-open と同罪）／E2E を「アプリがまだ薄いから」で省く
  （薄いうちに貫通1本を立てるのが一番安い——コードよりゲートが先、の実行時版）。

### Step 9 — CI（最終防衛線）
- 作る: ワークフロー——`pre-commit run --all-files`（冒頭に setup-uv）／言語ごとの
  テスト・解析ジョブ／ツールチェーン固定（`.python-version` は済み。各言語の版と
  ビルド必須環境変数の検証——§5 相当）。
- 完了条件: ① 正常 PR で全ジョブ緑 ② **GitHub の Web エディタから**違反を1件コミット
  した検証ブランチの PR が赤（ローカルフックが存在しない正規経路であり §2 の迂回禁止に
  抵触しない——まさに CI が守る「別マシン」シナリオの実測）③ 検証ブランチの削除
  ④ red-first（列を配線した場合——§5）: 親でも緑のテストを fix に同梱した検証 PR が
  **ジョブ赤**（exit 1）・正しい fix で証明1行＋緑・`RED-FIRST-EXEMPT`（理由あり）で
  免除1行・理由なし EXEMPT は免除不成立で赤のまま。仕上げにブランチ保護の
  required checks へ **3コアジョブ（`checks`・`red-first`・`commit-msg-history`）**を
  登録する（required の完成はリポジトリ設定まで — v2.9。最低線を3ジョブとする理由は
  §3.5——Web 編集・フック未導入経路では CI ジョブが唯一の強制点。**登録の有無は
  check-bootstrap が `gh api` で実測検証する**——検証不能環境は表示して素通し・検証できて
  不在なら本 Step は ✅ にできない — §3.5・v2.35〜v2.37）。登録は **rulesets 側を推奨**
  （CI の GITHUB_TOKEN で照会できるのは rulesets のみ＝CI 再監査が確定判定になる — v2.36）。
- ありがちなサボり（禁止）: 緑だけ確認して赤の実測を省く。

### Step 10 — 総合セルフ監査と引き継ぎ
- やる: ① 本チェックリスト全行が「実装と同一コミットで ✅ 化」されているかを
  コミット履歴で確認 ② `git grep` で `TODO` 0件・C の固有名詞 0件 ③ §3.3 相当の
  **全規則IDについて**「違反注入で落ちた」実績が Step 2〜8 のどこかにあるか、規則ID一覧と
  突き合わせる ④ ブートストラップに含めなかったプロジェクト固有の防止策（E2E・
  カバレッジ等）を移植先の §10 に Phase として 🚧 登録する。
- 完了条件: ①〜④すべて。ここで移植完了——以降は移植先の §10 と運用ルールに従う。
  完了報告では `.guardrails/CUSTOMIZE.md`（導入後にカスタムできる項目の索引 — v2.21）の存在を案内する
  （機構は揃っていても存在を知らせる導線が無いと発見されない、という穴の是正 — G9）。

---

## 12. ランタイム契約（手・目・土台）——静的工程と直交する、実行時の言語なし契約

§1〜§9 が「編集→commit→push→CI」の静的工程を守るのに対し、本節は**開発ループ中の
実行時**を契約化する。エージェントがバグを再現し・直し・検証するループの3要素——
**手**（環境と実UIを操作できる）・**目**（結果を機械可読に観察できる）・**土台**
（毎回同じ状態から始められる）——を言語なしで規定し、具象値はすべて採用列
（`bindings/catalog.md`）に置く。

### 12.1 共通動詞（手の入口・G2）✅（ルーターは配置済み・配線は列充填）
- **`scripts/dev.py` が全プロジェクト共通の動詞**を提供する:
  `up` / `reset` / `seed` / `time` / `test` / `e2e` / `fmt` / `check` / `probe` / `db` /
  `selftest` / `doctor`（v2.42・Phase 44）/ `gates`（v2.43・Phase 45）/
  `dod`（v2.45・Phase 47——列の違反注入コーパス再生。§11 Step 0）。
  **`gates` は「このキットが何をできるか」への正規の入口**——門の台帳
  （`repo_scan.py` の `GATE_REGISTRY`）を、このリポジトリでの実状態
  （常時有効／充填済み／未充填／配線済み）つきで一覧表示する。手書きの機能一覧を
  持たないための機構で、台帳と検査器コードの一致は `gates-registry-drift`（§3.3・hard）が
  機械検査する。発見の経路は README（主目的）→ `dev.py gates`（実状態つき全機能）→
  本書の各節（契約の詳細）の3段。
  `probe "<cmd>"` は迂回防止（§2）への事前照会——実行前に ALLOW / DENY と理由を返す
  （check と同じく言語なしで即動く kit-native 動詞 — v2.4）。
  `probe --live` は**実ホスト経路の発火確認**（Phase 44——§2 の live probe。nonce 入り
  sentinel 違反のブロックが違反ログ §3.6 に記録されたことを機械確認する2段階フロー。
  コーパス再生が証明しない「実セッションでハーネスがフックを発火させているか」を埋める）。
  `selftest` は門の違反注入コーパス一括再生（guard コーパス＋所有権ガード＋Codex フックの
  3チェッカ——門のテストの1動詞化）。`doctor` は環境診断の集約フロント（ツール・シム・
  フック配線・違反ログの事実表示 → check 実行。**新しい検査は作らない**——検査の正本は
  check の2スクリプト。§7.3 の重複実装禁止。**doctor は check を内包する**——監査手順で
  doctor の直後に check を重ねて実行しない。多重実行の削減 v2.45）。
  充填は dev.py 内の管理区画（`>>> GUARDRAILS BINDING >>>`）で **`COMMANDS.update({...})`
  の加算形のみ**——全置換は既定配線（check/probe/selftest）を消すため禁止（Phase 44）。
  動詞の**意味論は全プロジェクトで固定**、配線（実コマンド）だけが列ごとに違う——
  初見のエージェントが AGENTS.md §0 だけで環境に到達できることが判定基準（G2）。
- 各動詞は**冪等**（`up` を2回叩いても壊れない）。冪等性は配線先コマンドの責務。
- **未配線の動詞は明示エラーで落ちる**（静かに何もしない fail-open の禁止——§2 と同思想）。
- コマンド名（PATH 上の名前）は `shutil.which` で解決してから実行する（Windows の
  `.cmd`/`.bat` ランチャーは shell=False の直呼びでは起動できない——§7.2 の趣旨）。
  未導入は導入先（README/採用列の前提ツール欄）を示す明示エラー。
  「該当なし」の判断はカタログの列とD表に記録して初めて有効。
- 出力形式は `[dev] 動詞: コマンド` → `[dev] 動詞: exit N (+Xms)`（AGENTS.md §7 のログ形式）。

### 12.2 決定性の供給（土台・G1）（列充填）
- §9 が非決定の**禁止**（検出）を担うのに対し、本項は**供給**を担う——禁止だけでは
  エージェントは代替手段を持てない。
- **`reset` は seed 込みで既知状態へ戻す1コマンド**であること。完成条件は
  「`reset` → 同一操作2回 → 観察可能な状態（DB・UI）が一致」の実測（Step 8b DoD）。
- **時刻は注入シームで供給する**: アプリは現在時刻を直接読まず、`dev.py time <ISO8601>` で
  凍結できる Clock 抽象を1箇所持つ（締め切り・日跨ぎ・月末のバグ再現が1コマンドになる）。
- 乱数を持つ構成は seed を引数/環境で注入できること（§9.1 のラッパーはその一形態）。

### 12.3 観察レール（目・G4）（列充填）
- エージェントが**実行結果を機械可読に読める経路**を最低3つ持つ:
  ① アプリログ（§8.2 の単一出口——形式が固定なので grep 可能）
  ② ランタイムのコンソール・ネットワーク（Web 列なら Playwright MCP の読取機能）
  ③ 永続状態（`dev.py db "<読み取りクエリ>"`——ローカルDB限定・読み取り用途）。
- 「動いたはず」を禁止し「観察した」に置き換えるための機構——§10 実行規律 3
  （完了=実行結果）の実行時版。

### 12.4 操作レール（手・G2/G6）（列充填）
- **エージェントが実UIを操作できる手段**を1つ確立する。Web 列は Playwright MCP
  （`.mcp.json` に配線。`.claude/settings.json` の `enableAllProjectMcpServers` が
  プロジェクト定義の MCP を有効化する）。CLI 列は「そのまま実行」で足りる。
- **MCP の採用は許可リスト制（v2.11——2026-07-07 調査の判定を門に固定）**: プロジェクト
  正本（`.mcp.json`）に置いてよいのは操作レールの **Playwright MCP のみ**。ツール定義の
  常駐はコンテキストを食い（G3）、書込可能ツールは門の外の変更経路（G7）、CLI がある
  サービスは CLI が桁違いに安い（例: GitHub は `gh`）——判定の正本はカタログの
  「MCP・エコシステム採用規律」、機械強制は §3.3 `mcp-not-allowed`。性能調査等の
  スポット用途は `.mcp.json` に入れず **タスク単位の `claude mcp add` → 作業 →
  `claude mcp remove`**（保留の運用形——§10 保留節。常駐させないこと自体が判定）。
- **UI の操作要素にはテストID属性を必須にする**（採用列の `ui-missing-testid` が hard で
  強制）。エージェントの操作は推測クリックではなくテストID/アクセシビリティ属性の指名で
  行う——UIリファクタでE2Eと操作手順が壊れない（G6: 変更面の最小化）。
- E2E は操作レールの資産化: **再現できたバグは修正前に E2E spec 化**し、fix と同一
  コミットに含める（§3.4 のテスト判別に E2E パスを含めることで機械強制——G10）。

### 12.5 外部I/Oの検疫（土台・G8）
- 契約は §9.5。ランタイム側の含意: ローカル開発は**フェイクで完結**できること
  （`up` が外部サービス無しで立つ）。外部I/Oが無いと動かない開発環境は、決定性（G1）と
  ループ速度（G11）の両方を壊す。

### 12.6 中核不変条件の強制層（G7）
- Step 0 のD表で**このアプリ固有の「壊れたら致命」の性質**を列挙し、それぞれを
  **どの層が機械強制するか**（DB権限・型・§3.3 の hard 検査・CI）を明記する。
  例: 「打刻は追記のみ」→ DB の GRANT で UPDATE/DELETE を誰にも与えない（規約でなく権限）。
- 検査で強制するものは §3.3 の `REQUIRED_CONTENT_RULES` 等へ、権限・型で強制するものは
  その定義ファイルの所在を CLAUDE.md に記録する。「読んで守る」に残すのは機械化不能な
  ものだけ（§8.3 と同じ境界の引き方）。

### 12.7 バインディングカタログの運用（G5/G13）✅
- **具象値の正本は `bindings/catalog.md` の列**（列ID@版）。契約（本書）には具象値を
  書かない——現れる場合は「移植元の例」と明示された参照値。
- **刻印**: 採用列を決めたら、対象ファイル（`repo_scan.py`・`dev.py`・
  `.pre-commit-config.yaml`・`guardrails-ci.yml`・`post_edit_format.py`）のヘッダーに
  `BINDING-SOURCE: 列ID@版` を刻む。不一致は `HARD:binding-drift`、未刻印は
  `SOFT:binding-unstamped`（§3.3——出荷状態では後者が出るのが正常）。
- **還元**: 採用先で列の値を直したら、カタログへ**版上げで還元**する。採用先ローカルの
  黙修正は禁止（ドリフトの人間版）。「要実測」の列は、採用先の Step DoD 通過をもって
  「実測済み」へ昇格し、実測元を列末尾に1行残す。

## この文書自体の運用ルール

- **✅ の正本はここではない**——`.pre-commit-config.yaml` ・ `.claude/` 配下 ・ 各 `CLAUDE.md`
  ・ `.github/workflows/guardrails-ci.yml` ・ `scripts/` 配下が変わったら、このファイルの該当
  セクションも**同じコミットで**直す。
- **🚧 の正本は本書**——実装したら、その実装コミットで該当節を ✅ に更新し、
  §10 の状態表と Phase 記述を更新する（完了 Phase の DoD 詳細は消してよい。状態表の行は残す）。
- **契約と実装の乖離**——どちらが正か判断して同一コミットで両方を揃える。
- **新規リポジトリへの移植は §11**——進捗の正本は移植先に複製した Step チェックリスト。
  移植先で契約を緩めた場合は、その差分を移植先 .guardrails/GUARDRAILS.md に明記する。
- 新しい出戻り防止機構を追加したら、**3点セット**で更新する:
  ① 正本ファイルそのもの（未実装なら §10 に Phase 追加） ② 本書の対応する節
  ③ 冒頭 §0 の一覧表。
- **変更は `.guardrails/GOALS.md` の G を引用する**——本書・キット・カタログへの変更コミット/PRの
  本文に「どのGに効くか」を1行書く。どのGにも効かない変更は入れない。
- **列の値の変更は `bindings/catalog.md` へ版上げで還元する**（§12.7）。
