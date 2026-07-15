# guardrails-workbench

[guardrails-kit](https://github.com/zappyzed100/guardrails-kit) をベースに、UI 機能を追加していくためのワークベンチです。

- どの UI 機能を実装するかは guardrails-kit のコードを読み込んだうえで検討します(検討中)。
- UI Skill として [emilkowalski/skills](https://github.com/emilkowalski/skills) の全5スキル(`animation-vocabulary`・`apple-design`・`emil-design-eng`・`improve-animations`・`review-animations`)を採用しています。
- [voltagent/awesome-design-md](https://github.com/voltagent/awesome-design-md) は参照資料、[nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) は評価待ち候補として [.upstream/sources.yaml](.upstream/sources.yaml) に記録しています(選定理由も同ファイルに記載)。

## 構成

```
guardrails-workbench/
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

## 上流の更新フロー

上流ごとの取り込み・更新方式は [.upstream/sources.yaml](.upstream/sources.yaml) に記録しています。

| 上流 | 取り込み | 更新 |
|---|---|---|
| `zappyzed100/guardrails-kit` | submodule(全体) | **Dependabot** が週1で最新 commit への更新 PR を作成 |
| `emilkowalski/skills` | submodule + sparse-checkout | **update-ui-skills.yml** が週1で監視し、採用 Skill のパスに差分がある場合のみ更新 PR を作成 |

`update-ui-skills.yml` の判定ロジック:

1. 現在固定中の submodule SHA と上流 `main` の最新 SHA を比較
2. 同一なら何もしない
3. 異なる場合、`git diff --quiet <current> <latest> -- skills/emil-design-eng skills/review-animations` で採用パスの差分を確認
4. 採用パス外の変更のみなら何もしない。採用パスに差分があれば submodule SHA を更新する PR を作成

Dependabot は全 submodule を対象にするため、`dependabot.yml` の `ignore` で
`emilkowalski-skills` を除外し、こちらは上記 Action のみで管理しています。

## 新しい上流 / Skill を採用するとき

1. `.upstream/sources.yaml` に選定結果を追記
2. sparse-checkout 対象なら `scripts/setup-upstreams.ps1` のパス定数と
   `update-ui-skills.yml` の `ADOPTED_PATHS` を同期
