# Phase2 テスト設計fix

## 1. 追加するテスト

なし。プロジェクト規則によりテスト変更は事前確認が必要であり、今回は既存機能の表示階層変更を既存テストと実ブラウザで検収する。

## 2. 修正する既存テスト

なし。`ConsistencyTests.test_landing_page_html_contains_the_demo_without_javascript` が主要デモ内容の静的HTML残存を検証する。

## 3. 削除する旧仕様テスト

なし。

## 4. 手動確認項目

- デスクトップ幅でfeatured cardとCTAが明確に見える。
- モバイル幅でヘッダー、featured card、table/card表示がはみ出さない。
- real-world全27 cyclesとhistorical memoriesを展開できる。
- featured incidentを開き、未分析→Analyze→82%結果を表示できる。
- detailsを展開し、chart、timeline、causes、signals、similar incidents、evidenceを確認できる。
- evidence chipで証拠detailsが開き、対象行に移動する。
- seeded/captured/real-worldラベルと注意書きが残る。
- ブラウザconsoleにfatal errorがなく、APIに予期しない4xx/5xxがない。

## 5. 回帰確認項目

- 既存43テストが全件PASS。
- Python/JavaScript構文確認がPASS。
- 静的プリレンダーに既存テスト対象語句が残る。
- Analyze/Re-run、incident links、table row navigation、tooltip、detailsの操作が機能する。

## 6. 実行するテストコマンド

```text
cd backend
/Users/kimura/Projects/incident_memory/.venv/bin/python -m unittest discover -s tests
```

加えて `node --check frontend/app.js`、`python -m py_compile scripts/prerender.py`、ローカルfixtureブラウザ確認を実施する。

## 7. 実行しないテスト

Terraform plan/applyとAWSデプロイは実施しない。UIのローカル変更であり、applyはユーザーの別確認が必要。

## 8. 失敗時に実装を止める条件

- 既存テストが1件でも失敗。
- 既存の情報または操作がDOMから消える。
- evidence jump、Analyze、incident navigationのいずれかが失敗。
- デスクトップまたはモバイル表示に横スクロール以外の重大な崩れ。
- fatal console errorまたは予期しないAPI 4xx/5xx。

## 9. ブラウザ動作確認設計

- URL: fixtureモードのローカルサーバー。
- Desktop: dashboard→featured incident→Analyze→primary result→各details→evidence jump。
- Mobile: 390px幅でdashboardとanalysis上部を確認。
- Expected: STEP 1完了条件を満たし、全情報と全操作が残る。

## Gatepath 固有確認項目

| 確認項目 | 判定 |
|---|---|
| ACL fail-closed / fail-open 防止 | 影響なし。認証・認可・API処理は変更しない。 |
| OpenSearch bulk partial failure | 影響なし。OpenSearchを使用しない。 |
| watermark 不正前進 | 影響なし。同期処理を変更しない。 |
| orphan cleanup / full sync | 影響なし。削除・同期処理を変更しない。 |
| MCP 認証情報 | 影響なし。MCP経路を変更しない。 |

## テスト保証マトリクス

対象外。Bランク指摘やテスト保証不足修正ではない。
