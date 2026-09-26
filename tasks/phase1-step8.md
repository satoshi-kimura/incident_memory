# Phase1 差分要約

## 1. 仕様fixの要点

公式の Startup lane タグを `#startup` に統一し、審査員が冒頭30秒で「実AWS証拠→異なる原因への82%一致→前回の復旧策と14分回復」を理解できるコピーへ変更した。機能、データ、スコア、AWS構成は変更していない。

## 2. テスト設計fixの要点

既存43テスト、Python/JavaScript構文確認、タグ検索、Builder Center本文の文字数、ローカルfixtureのブラウザ確認で回帰を検証する設計とした。テストコードの変更は不要と判断した。

## 3. 変更ファイル一覧

- `README.md`: lane表記と冒頭説明を統一。
- `docs/SUBMISSION.md`: `#startup`、Startup lane、価値先行の冒頭説明へ変更。
- `docs/BUILDER_CENTER_BODY.md`: 提出本文のタグ・lane・冒頭説明を変更し、2,911文字に収めた。
- `docs/BUILDER_CENTER_POST.md`: 詳細版のタグ・lane・冒頭説明を変更。
- `frontend/app.js`: JavaScript版ランディングページのヒーローコピーを変更。
- `frontend/index.html`: JavaScriptなしの静的ヒーローコピーを変更。
- `scripts/prerender.py`: 次回生成される静的コピーを同じ内容へ変更。
- `tasks/phase1-step0.md`, `tasks/phase1-step1.md`, `tasks/phase1-step2.md`, `tasks/phase1-step3.md`, `tasks/phase1-step8.md`: phase-gate記録。

## 4. 本体実装の変更内容

抽象的な「Have we seen this before?」中心の説明を、「When AWS fails, remember what worked last time.」と具体的なデモ成果中心の説明へ変更した。実証済みの82%、異なる原因、共通シーケンス、前回のrollback、14分回復だけを使用した。動的UI、プリレンダー生成元、現在の静的HTMLを同じ文言にした。

自己レビューでは、ACL、認証、API互換性、マルチテナント、リソース、例外処理への変更がないことを確認した。orphan cleanup、watermark、lastSyncStatus、enabled、fail-open、null、OpenSearch、Secretの各失敗パターンはすべて対象外である。

## 5. テスト変更内容

テスト変更なし。既存の `ConsistencyTests.test_landing_page_html_contains_the_demo_without_javascript` を含む全テストを回帰確認に使用した。

## 6. テスト結果

- Python構文確認: PASS
- JavaScript構文確認: PASS
- unittest: 43件 PASS、0件 FAIL、0件 SKIP
- `git diff --check`: PASS
- 旧タグ・旧冒頭コピー検索: 0件
- `docs/BUILDER_CENTER_BODY.md`: 2,911文字、3,000文字未満

## 7. Gatepath 固有確認項目の結果

- ACL fail-closed: 影響なし
- watermark: 影響なし
- orphan cleanup: 影響なし
- OpenSearch bulk failure: 影響なし
- MCP認証: 影響なし

## 8. 残課題

なし。AWSへのデプロイは今回の依頼と権限範囲に含めず、実施していない。

## 9. 次フェーズに送るべき事項

公開サイトへ反映する場合は、プロジェクト正本の `build → terraform plan → ユーザー確認 → apply` 手順を別途実施する。

## 10. 今回増えた技術的負債

なし。

## 11. テスト保証マトリクスの検収結果

対象外。Bランク指摘・レビュー修正・保証不足修正ではない。

## 12. ブラウザ動作確認結果

| 項目 | 内容 |
|---|---|
| 判定 | PASS |
| 対象URL | `http://localhost:8011/` |
| 使用したブラウザMCP | Codex in-app browser |
| 実行した操作 | ランディングページを開き、主要インシデントを開き、Analyze Incidentを実行 |
| 期待結果 | 新コピー、82%一致、前回の復旧内容が表示され、画面遷移が成功する |
| 実際の結果 | 新コピー表示、分析API 200、INC-0012との82%一致、SEEDED DEMO、previous action、14分回復を確認 |
| API/Webログ確認 | GET/POSTはすべて200。ブラウザのwarning/errorは0件 |
| 残課題 | なし |
