# AGENTS.md — プロジェクト規約(このリポジトリで作業する**すべての**エージェントと人間の共通ルール)

本書が規約の正本。Codex / Cline / Cursor / Windsurf 等はルートの本ファイルを直読みし、
Claude Code は `CLAUDE.md` 冒頭の `@AGENTS.md` インポート経由で読む(.guardrails/GUARDRAILS.md §6。
本文をどちらかへ複製しない——分割であって複製ではないのがドリフトしない理由・G5)。
コミット・push・CI の門(.guardrails/GUARDRAILS.md §3〜§5)は git フックと CI なので**全エージェント共通**。
Claude Code と Codex が持つ追加の門(編集直後・操作直前・ターン終了のフック層)は、前者は
`CLAUDE.md`、後者は `.codex/hooks.json` を参照。Codex では `/hooks` でプロジェクトフックを
レビューして信頼してから有効になる。

**現状(2026-07-16)**: このリポジトリはガードレールキットの導入(Step 1)途上で、実装コード
(app/ 等)はまだ存在しない。[history_radio_spec_v0_4.md](history_radio_spec_v0_4.md) が
将来実装する「歴史スライド動画・自動生成ツール」の仕様書で、採用スタック(Step 0 の
言語・バインディング列選定)はまだ確定していない。§0・§5 のスタック依存部分は
実装開始時に確定する。

## §0 よく使うコマンド(ランタイム共通動詞 — .guardrails/GUARDRAILS.md §12.1)
すべて `uv run scripts/dev.py <動詞>`。動詞名は全プロジェクト共通・未配線は明示エラー
(採用列: 未定——Step 0 でスタック確定後に選ぶ。現時点で配線済みなのは
check/probe/selftest/dod のキット既定動詞のみ):

| 動詞 | 何をするか |
|---|---|
| `up` | ローカル環境を起動する(冪等) |
| `reset` | 既知状態へ戻す(seed込み — §12.2) |
| `seed` | シードデータ投入 |
| `time <ISO8601>` / `time clear` | アプリ内時刻の凍結/解除 |
| `test` | 単体テスト |
| `e2e` | E2E(実UI貫通) |
| `fmt` | 整形(冪等) |
| `check` | 構造検査(§3.3) |
| `probe "<cmd>"` | 迂回防止(§2)への事前照会——実行前に ALLOW/DENY と理由を返す |
| `db "<SQL>"` | ローカルDBの読み取り(観察レール — §12.3) |

- 索引再生成: `uv run scripts/generate_structure.py`(STRUCTURE.md を書いてよい唯一の主体)
- 静的解析: 未定(採用列の解析コマンド。pre-push で自動実行される)

## §1 ファイル規模
1ファイル500行以内を目安とする(超過は check-structure の soft 警告)。超えそうなら分割する。

## §2 フォルダ規模
1フォルダに CLAUDE.md 以外で7ファイルまでを目安とする(`scripts/` は例外)。
超えそうならサブフォルダへ整理する。

## §3 ファイル先頭ヘッダー
すべてのコードファイルの先頭に役割一行コメントを書く。書式: `<ファイル名> — 役割`
(例: `// main.dart — アプリのエントリポイント`、`# check_structure.py — 構造検査`)。

## §4 ドキュメントの置き場の分担
- 索引 = `STRUCTURE.md`(自動生成・手編集禁止)
- 設計根拠 = ルート `PLAN.md`(全体計画・機械可読タスク一覧)＋
  [docs/plans/development-plan.md](docs/plans/development-plan.md)(フェーズ別詳細タスクと検証コマンド)。
  **`PLAN.md` を編集する時は、必ず
  [docs/plans/PLAN_FORMAT.md](docs/plans/PLAN_FORMAT.md) の節構成・タスク記法(機械可読
  チェックリストの書式)に従うこと**——別プロジェクト(Progress Proof)が本リポジトリの
  `PLAN.md` を正規表現でパースして横断ダッシュボードに使うため、節見出しやタスク行の
  書式(チェックボックス＋行末の状態タグ)を崩すと収集側が解釈できなくなる。
  plan は**小さなタスク(目安: 1タスク数分)＋各タスクの検証コマンド**で書くと、
  中断・再開とレビューに強くなる(心得)。**レイヤー直下に新規ディレクトリを作る
  `feat:` は、設計根拠(`PLAN.md` / `docs/plans/`)の差分を同コミットに含める**
  (hard `feat-without-plan` が exit 1 でブロック — .guardrails/GUARDRAILS.md §3.4 検査5・G14。
  根拠は1行でよい。根拠を書けない構造変更は feat でなく refactor / chore を名乗る)
- 導入手順 = `README.md`
- 技術選定理由 = [docs/plans/development-plan.md](docs/plans/development-plan.md) §1
- フォルダ固有知見 = 各フォルダの `CLAUDE.md`
- 出戻り防止の地図 = `.guardrails/GUARDRAILS.md`
- 目標の正本 = `.guardrails/GOALS.md`(規約・キットへの変更はGを引用する)
- バインディングの正本 = `bindings/catalog.md`(採用列: 未定)

## §5 フォルダ独立性・依存方向
未定——実装コードがまだ無いため、レイヤー図・依存方向・禁止importはスタック確定時に
`bindings/catalog.md` の採用列から転記し、`check-structure` の hard `layer-violation` と
同じコミットで有効化する。

## §6 プロジェクト規約(vendor 領域・upstream)

`upstream/` 配下は読み取り専用の submodule(参照元)。編集しない。

### UI スキル(`.claude/skills/` — ベンダー領域)

[.claude/skills/](.claude/skills/) は
[nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
からのベンダーコピー(オーケストレータ + サブスキル6つ)。**手で編集しない**。
出所 SHA と更新手順は [.upstream/sources.yaml](.upstream/sources.yaml)(id: ui-ux-pro-max-skill)が正本。

採用時の特別対応3点(2026-07-15 決定・経緯は sources.yaml の rationale)。
いずれも管理区画(`>>> GUARDRAILS BINDING >>>`)への機械充填で、
**適用は `scripts/install_workbench.py` が行う**(手貼り不要。下のコードは充填内容の正本)。
kit の `install_kit.py` は版上げ時に区画の中身を引き継ぐため、充填は更新で消えない:

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

### デザイン参照資料

UI の見た目・方向性を検討・実装するときは
[upstream/design-md/awesome-design-md/design-md/](upstream/design-md/awesome-design-md/design-md/)
を参照する——74ブランド分の実在デザインシステムの DESIGN.md 集
(submodule + sparse-checkout。例: `design-md/apple/DESIGN.md`・`design-md/linear.app/DESIGN.md`)。
ui-ux-pro-max の検索(スタイル・パレットの一般則)と役割が違い、こちらは
「実在ブランドの具体的なトーン・トークン・原則」を引く時に使う。

## §7 ログ規則
- 秘匿: トークン・パスワード・APIキーをログに渡さない(コミット面は gitleaks が機械検査。
  ログ面はこの規約が最後の責務 — .guardrails/GUARDRAILS.md §8.3)。識別子は載せてよいが中身は載せない。
- 例外を握りつぶさない(空 catch 禁止 — lint で error 化)。
- 出力基準・形式: `[タグ] 操作名: 詳細 (+Xms)`。出口は単一化する
  (未定——採用スタック確定時に「ログ単一出口」を bindings/catalog.md の採用列から転記する)。
  他ファイルでの print 系直呼びは hard `log-direct-call`。
- I/O・外部呼び出し・エラーハンドラの境界(未定——採用列の「ログ境界パターン」)は前後5行以内に
  `logOp` 呼び出しか `// NO-LOG: 理由` コメントのどちらかを書く(soft `missing-log-coverage`
  — .guardrails/GUARDRAILS.md §8.4)。**「この処理は重要だからログすべき」の判断は人間の仕事のまま**
  ——機械が検査するのは存在だけで、`NO-LOG:` の理由の妥当性は検証しない。**レビューでは
  `NO-LOG:` の使用を必ず点検する**: 理由が具体的か・空虚な言い訳になっていないか
  (RED-FIRST-EXEMPT の乱用監視と同じ運用 — .guardrails/GUARDRAILS.md §8.4・§10 Phase 31)。

## §8 テスト戦略
- テストが通る状態でのみコミットする(pre-push と CI が機械検査)。
- 一度直したバグは回帰テストに固定し、fix と同一コミットに同梱する
  (commit-msg フックの `fix-without-test` が機械検査)。
- **新機能(feat)もテストを同梱する**——テストが書けない feat は設計を疑う
  (soft `feat-without-test` が警告で可視化 — .guardrails/GUARDRAILS.md §3.4 検査6)。
- テストの重心は**リファクタリングで壊れない統合水準**に置く——モックの挙動だけを写した
  単体テストは実装の複製であり、守っているのはコードでなく書き方(心得)。
- LLM に書かせたテストは happy-path の自己検証に寄りやすい——**境界値と異常系を明示して
  発注**し、レビューではテストが「仕様」を主張しているか(実装の写しでないか)だけ見る(心得)。
- fix の同梱テストは**親コミットで赤**でなければならない(CI の `red-first` ジョブが
  機械証明・required — .guardrails/GUARDRAILS.md §5)。CI 上で赤にできない修正だけ、本文に
  `RED-FIRST-EXEMPT: 理由` を書く(理由は必須——空は無効)。**レビューでは EXEMPT の
  使用を必ず点検する**: 理由が具体的か・本当に CI 上で再現不能か・頻度が増えて
  いないか(乱用監視——required 運用の条件。.guardrails/GUARDRAILS.md §10 Phase 21)。
- flaky の温床を持ち込まない: テスト内の sleep・現在時刻・seed なし乱数・外部I/O直呼びは
  hard 違反(`test-sleep` / `test-nondeterminism` / `test-network`——時刻は Clock 抽象、
  乱数は seed、外部I/Oはフェイクを注入する — .guardrails/GUARDRAILS.md §9.5・§12.2)。**非決定性の
  再現そのものがテストの本質という正当なケース**(実タイミング競合の再現テスト等)は、
  該当行の前後3行以内に `NONDETERMINISM-EXEMPT: 理由` コメントで免除できる(理由は
  必須——空は無効。**レビューでは EXEMPT の使用を必ず点検する**: `NO-LOG:` /
  `RED-FIRST-EXEMPT:` と同じ乱用監視 — .guardrails/GUARDRAILS.md §9.5・§10 Phase 35)。
- 確率的コンポーネントが有る場合: テストは `xxx_for_test(seed, timeout)` ラッパー経由のみ。
- 本命の E2E: 未定(採用列のE2E。`uv run scripts/dev.py e2e`)。**再現できたバグは修正前に
  E2E spec 化**し、fix と同一コミットへ(E2E パスはテスト判別規則に含める — §12.4)。
- UI の操作要素にはテストID属性を必ず付ける(hard `ui-missing-testid` — §12.4)。

## §9 該当なし(現時点で追加の原本章なし)

## §10 Git 規則
- GitHub Flow: main へ直接 push しない。1トピック=1ブランチ=1PR。
- コミットは小さく(純変更 400 行超で soft `commit-too-large` が警告——生成物・lockfile は
  除外。大きな塊は「どの門が何を検証したか」を追えなくする — .guardrails/GUARDRAILS.md §3.4 検査7)。
- コミットメッセージ規約: `^(feat|fix|test|docs|refactor|chore): .+`
  (commit-msg フックが機械検査。Merge / Revert / fixup! / squash! は素通し)。
- 言語: コミットメッセージも PR(タイトル・本文)も日本語で書く。型接頭辞
  (`feat:` 等)・識別子・コマンド名はそのまま英語でよい。
- `.guardrails/GOALS.md`・`.guardrails/GUARDRAILS.md`・`bindings/catalog.md` を変更するコミットは、本文に
  効くGを1行書く(例: `docs: §3.3 に規則追加(G4)` — `governance-without-goal` が機械検査)。
- **依存は増えてよいが、黙って増えてはならない**: 依存マニフェスト(package.json /
  pyproject.toml / Cargo.toml / pubspec.yaml)に名前を足すコミットは、本文に
  `依存追加: <名前> — 理由1行` を書く(`undeclared-dependency` が機械検査 —
  .guardrails/GUARDRAILS.md §3.4 検査4。lockfile だけの更新・版上げは対象外)。

### §10-4 フック(commit / push の門)との付き合い方 — 全エージェント共通
pre-commit / commit-msg / pre-push の門は git フックなので、どのエージェントで作業しても発火する。
- 迂回禁止: `--no-verify`・`SKIP=` は使わない。フックが落ちるなら迂回せず違反そのものを直す
  (Claude Code では技術的にもブロックされる — CLAUDE.md。他エージェントでは本規約が心得として
  効き、CI(.guardrails/GUARDRAILS.md §5)が最終防衛線として同じ検査を再実行する)。
- 未コミットの作業を消すコマンド(`git reset --hard`・`git clean -f`・広域 checkout/restore)を
  使わない: 消してよい変更なら先に `git stash` で退避する(Claude Code では dirty 時に
  技術的にもブロック — .guardrails/GUARDRAILS.md §2 作業消失ガード。`.git` の削除は常に禁止)。
- 自動修正系フックで落ちたら: 書き換えられたファイルを `git add` して同じコミットを再実行するだけ。
- `generate-structure` で落ちたら: `git add STRUCTURE.md` して再実行するだけ。
- 同じフックが**2回連続**で落ちたら機械的リトライをやめて原因調査に切り替える。

## §11 該当なし(現時点で追加の原本章なし)

## §12 作業開始の定型手順
1. `STRUCTURE.md` を読む(いまの全体像)
2. [history_radio_spec_v0_4.md](history_radio_spec_v0_4.md) を読む(なぜこの構成か・実装前の仕様書)
3. 触るフォルダの `CLAUDE.md` を読む(フォルダ固有の知見・ハマりどころ)
4. 環境が要る作業なら `uv run scripts/dev.py verbs` で配線状態を確認する
   (未配線の動詞に当たったら .guardrails/GUARDRAILS.md §12.1——黙って回避しない)

## §13 発見の記録先(中央メモは作らない)
- 再現できるバグ → 回帰テスト(fix と同一コミット)
- 直感に反する箇所 → その場の近接コメント
- フォルダ固有の知見 → そのフォルダの `CLAUDE.md`
- **昇格ルール**: 近接コメントに書いた制約が**そのファイルの外**で噛んだら(別ファイルの
  テスト・コードを書く場面で同じ制約に落ちたら)、そのフォルダの `CLAUDE.md` へ昇格して
  記録する——ファイル内のコメントはそのファイルを開いた人にしか効かず、フォルダの入口に
  無い知見は次にそのフォルダを触る人/AI が毎回同じ穴に落ちる
