<!-- config/readings/README.md — 読み辞書の設定・自作辞書の置き場と運用手順 -->
# config/readings/ — 読み辞書の設定と自作辞書

置き場の分担（development-plan.md §8.3・§8.4）:

| ファイル | 役割 |
|---|---|
| `sources.yaml` | 全データソースのライセンス・出典表記の正本（THIRD_PARTY_NOTICES.md の生成元） |
| `eras.yaml` | 元号読み辞書（自作・約250件。年代/QIDはWikidata由来、読みは人手検証対象） |
| `manual.yaml` | 手動修正辞書（人間が検証した正。§8.4の後続タスクで導入） |

辞書データ**本体**（JMnedict等の外部辞書）はここに置かない——取得スクリプトが
`artifacts/readings/`（Git対象外）へソース別JSONLで保存する。

## NDL「ヨミガナ辞書」（PDF）の使い方 — 確認資料としてのみ

明治期の官職・行政用語の読みの**裏取り専用**（§8.1「慎重」区分）。次を守る:

1. PDFから抽出した辞書全体・一部の**再配布をしない**（`manual.yaml` へ機械的に
   流し込まない。artifacts/ へ変換保存もしない）
2. 使い方は「`manual.yaml` へ個別エントリを人手で追加する際の確認」だけ——
   追加するエントリには出典コメントを付ける:
   ```yaml
   - surface: 大蔵卿
     reading: オオクラキョウ
     kind: office
     context: null
     confidence: 1.0
     # 出典: NDLヨミガナ辞書で確認（2026-07-17）
   ```
3. レビュー観点: `manual.yaml` の差分に上記の出典コメントが付いているかを見る
   （機械検査はしない——目視レビューの手順として本READMEが正本）

## eras.yaml の人手検証

読みは歴史年表の通行読みで自作した初期値（`verified: false`）。一度通読して
正しければ `verified: true` に変える（confidence が 0.9→1.0 に上がる —
`readings/era_dictionary.py`）。誤りを直した場合も同様に true へ。
