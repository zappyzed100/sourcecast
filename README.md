# guardrails-workbench

[guardrails-kit](https://github.com/zappyzed100/guardrails-kit) をベースに、UI 機能を追加していくためのワークベンチです。

- どの UI 機能を実装するかは guardrails-kit のコードを読み込んだうえで検討します(検討中)。
- UI Skill として [emilkowalski/skills](https://github.com/emilkowalski/skills) の全5スキル(`animation-vocabulary`・`apple-design`・`emil-design-eng`・`improve-animations`・`review-animations`)を採用しています。
- [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) を `.claude/skills/` へベンダーコピーとして採用しています(7スキル。特別対応3点は [CLAUDE.md](CLAUDE.md) と [.upstream/sources.yaml](.upstream/sources.yaml) を参照)。
- [voltagent/awesome-design-md](https://github.com/voltagent/awesome-design-md) は参照資料として [.upstream/sources.yaml](.upstream/sources.yaml) に記録しています(選定理由も同ファイルに記載)。

## 構成

```
guardrails-workbench/
├─ .claude/
│  └─ skills/                      # ui-ux-pro-max のベンダーコピー(7スキル・手編集禁止)
├─ upstream/
│  ├─ guardrails-kit/              # submodule(リポジトリ全体を利用)
│  └─ ui-skills/
│     └─ emilkowalski-skills/      # submodule + sparse-checkout(採用Skillのみ)
├─ scripts/
│  ├─ setup-upstreams.ps1          # clone後のsparse-checkout再現スクリプト
│  ├─ install_workbench.py         # workbench分の機械インストーラ(導入方法ケース1/2/4)
│  └─ revendor_uipro.py            # ui-ux-pro-max の再ベンダー(導入方法ケース3)
├─ .github/
│  ├─ dependabot.yml               # guardrails-kit の更新(skillsはignore)
│  └─ workflows/
│     └─ update-ui-skills.yml      # 採用Skillのパス差分監視 → submodule更新PR
└─ .upstream/
   └─ sources.yaml                 # 上流選定結果の記録
```

## セットアップ(導入方法)

前提ツール(マシンに1回): git / uv / 対象言語のツールチェーン(ts-react-web 列なら Node.js)。
pre-commit は手順の中で自動導入されます。自分の状況に合うケースを1つ選び、
**書いてあるコードを実行し、プロンプトの★欄を埋めて貼るだけ**で完結します。

コマンドはすべて**導入先リポジトリのルートで**実行します——コマンド中のパスは
スクリプトの置き場所(submodule や一時 clone)を指しているだけで、書き込み先は常に
「いま居るディレクトリ」です(インストーラはそこが git リポジトリのルートでなければ停止する)。

| あなたの状況 | 使うケース |
|---|---|
| この workbench 自体を手元で触りたいだけ | ケース0 |
| まっさらな新しいリポジトリで始める | ケース1 |
| 既にコードがあるリポジトリに入れる | ケース2 |
| 導入済みのリポジトリに workbench の更新を取り込む | ケース3 |
| guardrails-kit だけ導入済みのリポジトリに UI 分を足す | ケース4 |

### ケース0: この workbench 自体を手元で触る場合

```powershell
git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git
cd guardrails-workbench
.\scripts\setup-upstreams.ps1   # sparse-checkout は clone で復元されないため再適用する
```

### ケース1: 新規リポジトリに導入する場合

1. workbench をテンプレートとして clone し、自分のリポジトリにして kit を配置する:

   ```powershell
   git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git <新リポジトリ名>
   cd <新リポジトリ名>
   .\scripts\setup-upstreams.ps1
   git remote set-url origin <新リポジトリの URL>
   uv run --no-project upstream/guardrails-kit/scripts/install_kit.py
   ```

2. `upstream/guardrails-kit/PROMPT_claude_code.md` を開き、冒頭の★欄を埋める
   (言語・確率的コンポーネントの有無・GitHub リモート URL 等)
3. このリポジトリで起動した Claude Code の**最初のメッセージ**として全文を貼る
   → エージェントが敷設(Step 0→10・1 Step = 1 ブランチ = 1 PR・違反注入 DoD)を完遂する。
   アプリの骨格はゲートが立った後に作る(違反ゼロから始める)
4. 仕上げに workbench 分(特別対応の充填)を適用する:

   ```powershell
   uv run --no-project scripts/install_workbench.py
   ```

### ケース2: 既存リポジトリに導入する場合

1. 対象リポジトリのルートで workbench を一時取得し、kit を配置する:

   ```powershell
   git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git .workbench-src
   uv run --no-project .workbench-src/upstream/guardrails-kit/scripts/install_kit.py
   ```

2. `.workbench-src/upstream/guardrails-kit/PROMPT_claude_code_existing.md` を開き、冒頭の★欄を
   埋める(既存コードの言語・触ってはいけない領域・既存テストの状態等。分からない欄は
   「コードから読み取って Step -1b で提案せよ」と書けばよい)
3. このリポジトリで起動した Claude Code の**最初のメッセージ**として全文を貼る
   → 棚卸しから敷設まで完遂する(違反が残る規則は一時停止+清掃 Phase 登録、
   既存の CLAUDE.md・CI・`.gitignore` 等とはマージであって上書きではない)
4. 仕上げに workbench 分を適用して後片付け:

   ```powershell
   uv run --no-project .workbench-src/scripts/install_workbench.py
   Remove-Item -Recurse -Force .workbench-src
   ```

**この workbench 自身に敷設する場合**も同じケースですが、clone は不要です(kit もインストーラも手元にある):

```powershell
uv run --no-project upstream/guardrails-kit/scripts/install_kit.py
# → PROMPT_claude_code_existing.md の★欄を下の表の値で埋めて貼る → 敷設完了後:
uv run --no-project scripts/install_workbench.py
```

| ★ | 値 |
|---|---|
| 採用するバインディング列 | `ts-react-web@12` |
| 確率的コンポーネント | 無 |
| 触ってはいけない領域 | `upstream/`(submodule)・`.claude/skills/`(ベンダーコピー) |
| 既存テストの状態 | なし(テストはまだ無い) |
| GitHub リモート URL | https://github.com/zappyzed100/guardrails-workbench |

### ケース3: 導入済みのリポジトリに workbench の更新を取り込む場合

更新は3経路あり、来た通知に応じて実行します:

**(a) guardrails-kit の新版**(検知: Dependabot の submodule 更新 PR)——PR を取り込んだあと:

```powershell
uv run --no-project upstream/guardrails-kit/scripts/install_kit.py       # 再実行(充填は引き継がれる)
```

続けて `upstream/guardrails-kit/PROMPT_claude_code_update.md` の★欄を埋めて Claude Code に貼る
(消えた充填の復元と、新しく増えた門ごとの違反注入確認まで自動で回る)。最後に追随を機械判定:

```powershell
uv run --no-project upstream/guardrails-kit/scripts/install_kit.py --check
```

**(b) emil UI スキル**(検知: update-ui-skills.yml の submodule 更新 PR)——PR を取り込むだけ。

**(c) ui-ux-pro-max**(検知なし。任意のタイミングで):

```powershell
uv run --no-project scripts/revendor_uipro.py
```

### ケース4: guardrails-kit だけ導入済みのリポジトリに UI 分を足す場合

プロンプトは使いません。対象リポジトリのルートでコマンドを実行するだけです:

```powershell
git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git .workbench-src
uv run --no-project .workbench-src/scripts/install_workbench.py --dry-run   # プレビュー(書き込みなし)
uv run --no-project .workbench-src/scripts/install_workbench.py            # 本適用
Remove-Item -Recurse -Force .workbench-src
uv run scripts/dev.py design "saas dashboard"                                # 動作確認
```

kit の版を揃える必要はありません(充填は管理区画がある全ての版で成立。区画の無い旧版だけ
CONFLICT で停止して案内が出るので、その時はケース3の (a) を先に実行)。

### 補足(全ケース共通)

- 2つのインストーラ(`install_kit.py` / [`scripts/install_workbench.py`](scripts/install_workbench.py))は
  どちらも**冪等**(再実行しても二重適用しない)・**黙って上書きしない**(衝突は CONFLICT で停止)・
  `--dry-run` でプレビューできる。ケース4の流れは kit 導入済みの模擬リポジトリで実測検証済み
- kit は「`upstream/` の原本」と「ルートの稼働コピー」に分離される。稼働コピーは直接手直しせず、
  kit リポジトリ側で直して版上げ→ケース3(a) で還元する(ドリフトは `install_kit.py --check` が検出)
- CI 実測(敷設の Step 9)までに GitHub 設定「Allow GitHub Actions to create and approve pull requests」を
  有効化しておく

## 上流の更新フロー

上流ごとの取り込み・更新方式は [.upstream/sources.yaml](.upstream/sources.yaml) に記録しています。

| 上流 | 取り込み | 更新 |
|---|---|---|
| `zappyzed100/guardrails-kit` | submodule(全体) | **Dependabot** が週1で最新 commit への更新 PR を作成 |
| `emilkowalski/skills` | submodule + sparse-checkout | **update-ui-skills.yml** が週1で監視し、採用 Skill のパスに差分がある場合のみ更新 PR を作成 |

`update-ui-skills.yml` の判定ロジック:

1. 現在固定中の submodule SHA と上流 `main` の最新 SHA を比較
2. 同一なら何もしない
3. 異なる場合、`git diff --quiet <current> <latest> -- <採用スキルのパス群>` で採用パスの差分を確認(パスの正本は [.upstream/sources.yaml](.upstream/sources.yaml) と workflow の `ADOPTED_PATHS`——現在は全5スキル)
4. 採用パス外の変更のみなら何もしない。採用パスに差分があれば submodule SHA を更新する PR を作成

Dependabot は全 submodule を対象にするため、`dependabot.yml` の `ignore` で
`emilkowalski-skills` を除外し、こちらは上記 Action のみで管理しています。

## 新しい上流 / Skill を採用するとき

1. `.upstream/sources.yaml` に選定結果を追記
2. sparse-checkout 対象なら `scripts/setup-upstreams.ps1` のパス定数と
   `update-ui-skills.yml` の `ADOPTED_PATHS` を同期
