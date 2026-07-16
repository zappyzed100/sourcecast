<!-- THIRD_PARTY_NOTICES.md —
読み辞書データソースの出典・ライセンス一覧（機械生成・手編集禁止） -->
# サードパーティ辞書データの出典とライセンス

本ファイルは `config/readings/sources.yaml` から
`uv run scripts/readings/generate_third_party_notices.py` で生成される（手編集禁止）。
辞書データ本体はリポジトリにコミットしない——取得スクリプトが取得日・件数・ハッシュを
記録する（development-plan.md §8.3）。ライセンス原文は `licenses/` に置く。

## サードパーティデータ

### デジタル庁 アドレス・ベース・レジストリ

- ライセンス: PDL 1.0（パブリック・ドメイン・ライセンス）
- ライセンスURL: https://www.digital.go.jp/policies/base_registry_address
- 配布元: https://catalog.registries.digital.go.jp/
- 出典表記: アドレス・ベース・レジストリ（デジタル庁）を加工して作成
- 派生辞書としての再配布: 可
- 備考: 現代地名の読み。出典と加工した旨の表示が条件（attribution_textが両方を含む）

### JMnedict (Japanese Multilingual Named Entity Dictionary)

- ライセンス: CC BY-SA 4.0
- ライセンスURL: https://creativecommons.org/licenses/by-sa/4.0/
- 配布元: https://www.edrdg.org/enamdict/enamdict_doc.html
- 出典表記: JMnedict © Electronic Dictionary Research and Development Group (CC BY-SA 4.0)
- 派生辞書としての再配布: 可
- 備考: 人名・地名の読み補完。SA継承が派生辞書へ及ぶため専用テーブルで分離管理し、他ソースと混ぜて再配布しない（§8.3）

### Web NDL Authorities（国立国会図書館典拠データ）

- ライセンス: 国立国会図書館の利用条件に従う（出典明示で利用可）
- ライセンスURL: https://id.ndl.go.jp/information/policy/
- 配布元: https://id.ndl.go.jp/auth/ndla
- 出典表記: Web NDL Authoritiesから取得（国立国会図書館）
- 派生辞書としての再配布: 不可
- 備考: 重要人物の読み・別名・生没年。出典明示が条件——attribution_textの文言を変えない

### SudachiDict (full)

- ライセンス: Apache-2.0
- ライセンスURL: https://www.apache.org/licenses/LICENSE-2.0
- 配布元: https://github.com/WorksApplications/SudachiDict
- 出典表記: SudachiDict © Works Applications Co., Ltd. (Apache License 2.0)
- 派生辞書としての再配布: 可
- 備考: 一般語・基本固有名詞。ライセンス文・著作権表示を保持する

### Wikidata (P1814: name in kana)

- ライセンス: CC0 1.0
- ライセンスURL: https://creativecommons.org/publicdomain/zero/1.0/
- 配布元: https://www.wikidata.org/
- 出典表記: Wikidata (CC0 1.0)
- 派生辞書としての再配布: 可
- 備考: 歴史人物・歴史地名・官職の読み補完。読み未登録の項目も多い

## 自作データ（本プロジェクトの資産）

### 元号読み辞書（自作・約250件）

- 置き場: config/readings/eras.yaml
- 表記: 元号読み辞書（history-radio自作。Wikidata・国立国会図書館資料を基に人手検証）
- 備考: Wikidata・NDL資料を基に一度人手で検証して自作する（§8.4の独立タスク）

### 手動修正辞書（自作）

- 置き場: config/readings/manual.yaml
- 表記: 手動修正辞書（history-radio自作）
- 備考: 人間が検証した正。文脈依存の複数読みを表現する（例: 判官=ホウガン/ハンガン）。外部由来と混ぜない（§8.3）。NDL「ヨミガナ辞書」PDFは確認資料としてのみ使い、由来エントリには出典コメントを残す
