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
│  └─ setup-upstreams.ps1          # clone後のsparse-checkout再現スクリプト
├─ .github/
│  ├─ dependabot.yml               # guardrails-kit の更新(skillsはignore)
│  └─ workflows/
│     └─ update-ui-skills.yml      # 採用Skillのパス差分監視 → submodule更新PR
└─ .upstream/
   └─ sources.yaml                 # 上流選定結果の記録
```

## セットアップ

```powershell
git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git
cd guardrails-workbench
.\scripts\setup-upstreams.ps1
```

sparse-checkout は git のローカル設定で `.gitmodules` には永続化されないため、clone 直後に
`setup-upstreams.ps1` を実行して `emilkowalski-skills` submodule を採用 Skill のみのチェックアウトにします。

## guardrails-workbench の導入方法

guardrails-workbench(= guardrails-kit + UI スキル一式 + 特別対応の記録)を対象リポジトリへ
導入する手順です。ガードレール本体の敷設は guardrails-kit が用意する **3種のプロンプト**
(正本: [upstream/guardrails-kit/README_SETUP.md](upstream/guardrails-kit/README_SETUP.md))に乗り、
workbench 固有分(UI スキルのベンダーコピーと特別対応3点)を上乗せします。

| 対象 | 使う kit プロンプト | 特徴 |
|---|---|---|
| まっさらな新規リポジトリ | `PROMPT_claude_code.md` | 骨格を作り、ゲートを先に立て、違反ゼロから始める |
| 既にコードがあるリポジトリ | `PROMPT_claude_code_existing.md` | 棚卸し→違反が残る規則は一時停止+清掃 Phase 登録→既存ファイルとはマージ |
| 導入済みリポジトリへ更新を反映 | `PROMPT_claude_code_update.md` | インストーラ再実行(UPGRADED)→充填の復元→新しい門ごとに違反注入 DoD |
| **kit 導入済み**リポジトリへ workbench を追加 | プロンプト不要(ケース4) | 敷設作業なし——充填2箇所+ファイルコピー+効きの確認だけの差分適用 |

### 共通: workbench 構成の持ち込みと kit の配置

対象リポジトリに workbench の構成一式を持ち込みます(新規リポジトリならケース1の
clone 方式が最短で、この手作業は不要):

1. **上流構成**: guardrails-kit の submodule(`upstream/guardrails-kit`)、emil UI スキルの
   submodule + sparse-checkout(`scripts/setup-upstreams.ps1`・`update-ui-skills.yml`・
   `dependabot.yml` を流用)
2. **UI スキル**: `.claude/skills/`(ui-ux-pro-max のベンダーコピー)をそのままコピー
   (再ベンダー手順は [.upstream/sources.yaml](.upstream/sources.yaml) に記載)
3. **記録**: [.upstream/sources.yaml](.upstream/sources.yaml) と [CLAUDE.md](CLAUDE.md)
   (特別対応3点の充填コード入り)を持ち込む

kit の配置は submodule が原本なので zip のダウンロード不要、1コマンドです:

```powershell
# プレビュー(書き込みなし。ファイルごとの判定と衝突の有無を一覧表示)
uv run --no-project upstream/guardrails-kit/scripts/install_kit.py --dry-run

# 配置の本番実行
uv run --no-project upstream/guardrails-kit/scripts/install_kit.py
```

インストーラの性質(実装確認済み):

- 既存ファイルを**黙って上書きしない**(衝突は CONFLICT で停止・`.gitignore` のみ区画追記のマージ)
- 後片付けの削除対象は `guardrails-kit*` という名前の階層のみ——**`upstream/` の submodule は削除されない**
- 配置されるのはルートの「稼働コピー」。原本は submodule のピンのまま分離される。
  稼働コピーを直接手直ししない(直すなら kit リポジトリ側で版上げ→submodule 更新→再インストールで還元。
  ドリフトは `install_kit.py --check` が機械検出し、CI にも載せられる)
- kit 原本判定マーカー(`.guardrails-kit-source`)は submodule 内にしか無く親リポジトリの
  追跡ファイルに現れないため、導入先が「kit 原本」と誤認されて検査が緩むことはない

前提ツール(ユーザーのマシンに1回): git + GitHub リモート / uv / 採用列の言語ツールチェーン
(ts-react-web 列なら Node.js)。pre-commit 本体は手順内で `uv tool install pre-commit` として導入されます。
CI 実測(Step 9)までに GitHub 設定「Allow GitHub Actions to create and approve pull requests」を有効化しておくこと。

### ケース1: 新規リポジトリに導入する場合

最短は **workbench を clone してリモートを差し替える**方式です(構成一式が最初から揃う):

```powershell
git clone --recurse-submodules https://github.com/zappyzed100/guardrails-workbench.git <新リポジトリ名>
cd <新リポジトリ名>
.\scripts\setup-upstreams.ps1
git remote set-url origin <新リポジトリの URL>
```

1. kit を配置する(共通の1コマンド)
2. `upstream/guardrails-kit/PROMPT_claude_code.md` の★欄(言語・確率的コンポーネントの有無・
   GitHub リモート URL 等)を埋める
3. リポジトリルートで起動した Claude Code の**最初のメッセージ**として全文を貼る
4. エージェントが `.guardrails/GUARDRAILS.md` §11 の Step 0→10 を実行規律
   (順序固定・**1 Step = 1 ブランチ = 1 PR**・違反注入必須・虚偽✅の機械検出)で完遂する。
   このとき workbench の特別対応3点([CLAUDE.md](CLAUDE.md) 記載)も同じ管理区画へ充填する。
   アプリの骨格はゲートが立った後に作る(違反ゼロから始める)

### ケース2: 既存リポジトリに導入する場合(このリポジトリ自身もこちら)

既にコードがあるリポジトリへは、共通の「構成の持ち込み+kit 配置」のあと、プロンプトだけ
`PROMPT_claude_code_existing.md` を使います。新規との違いは3点:
**棚卸し(Step -1)**で既存コードの違反を可視化する/違反が残る規則は
BINDING で一時停止し**清掃 Phase として §10 に登録**する(黙った無効化は禁止)/
既存の CLAUDE.md・CI・`.gitignore` 等とは**マージであって上書きではない**。

この workbench 自身に敷設する場合の★欄の答え:

| ★ | 値 |
|---|---|
| 採用するバインディング列 | `ts-react-web@12` |
| 確率的コンポーネント | 無 |
| 触ってはいけない領域 | `upstream/`(submodule)・`.claude/skills/`(ベンダーコピー) |
| 既存テストの状態 | なし(テストはまだ無い) |
| GitHub リモート URL | https://github.com/zappyzed100/guardrails-workbench |

加えて、[CLAUDE.md](CLAUDE.md) に記載の特別対応3点(`GENERATED_PATTERNS` 2行+
`dev.py` の `design` 動詞)を同じ管理区画へ充填します(貼るコードは CLAUDE.md にそのまま書いてある)。

### ケース3: guardrails-workbench が更新され、それを反映させる場合

導入先から見ると workbench の更新は3経路あり、それぞれ反映方法が決まっています:

| 更新元 | 検知 | 反映 |
|---|---|---|
| guardrails-kit の新版 | **Dependabot** の submodule 更新 PR | PR を取り込む → インストーラ再実行(kit 系統は **UPGRADED**——管理区画の充填は中身ごと引き継がれ、旧内容は git 履歴が安全網)→ `PROMPT_claude_code_update.md` を貼る(消えた充填の復元 → §10 の Phase 見出し diff で**新しく増えた門を列挙** → 門ごとに違反注入で効いていることを確認)。追随の判定は `install_kit.py --check`(全ファイル OK/KEPT/SKIPPED なら exit 0・CI に載せられる) |
| emil UI スキル | **update-ui-skills.yml** が採用パスに差分がある時だけ submodule 更新 PR | PR を取り込むだけ |
| ui-ux-pro-max | 手動(npm パッケージは GitHub main より遅れるため自動化しない) | [.upstream/sources.yaml](.upstream/sources.yaml) の再ベンダー手順で `.claude/skills/` を更新し `vendored-from-sha` を上げる |

### ケース4: すでに guardrails-kit を導入済みのリポジトリに workbench を導入する場合

3種のプロンプトはどれも「kit をどう敷くか/どう追随するか」のためのもので、このケースには
使いません(既存用プロンプトで Step 0→10 をやり直すのは丸ごと無駄)。workbench の上乗せ分は
敷設作業を伴わない差分なので、次の4手で済みます:

1. **kit の版を揃える**(前提確認): 導入先の kit が workbench のピンより古ければ、
   先にケース3の kit 更新フローで追随させる(判定は `install_kit.py --check`)
2. **UI 部分の持ち込み**: `.claude/skills/`(ベンダーコピー)をコピー/emil スキルの
   submodule + sparse-checkout 一式(`scripts/setup-upstreams.ps1`・`update-ui-skills.yml`・
   `dependabot.yml` の ignore 設定)を流用/[.upstream/sources.yaml](.upstream/sources.yaml) を
   持ち込み/[CLAUDE.md](CLAUDE.md) の UI スキル節を既存 CLAUDE.md へマージ
3. **特別対応3点の充填**: 既存の管理区画(`>>> GUARDRAILS BINDING >>>`)へ
   `GENERATED_PATTERNS` 2行(`scripts/repo_scan.py`)と `design` 動詞(`scripts/dev.py`)を
   足す(貼るコードは CLAUDE.md にそのまま書いてある。敷設済みなら区画はもうある)
4. **効きの確認**(違反注入 DoD と同じ作法): `check_structure` がベンダー領域
   (`.claude/skills/`)に発火しないこと・`uv run scripts/dev.py design "<query>"` が
   動くことを確認する

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
