# Phase1 編集対象ファイル

## 本体実装・表示

- `frontend/app.js`: JavaScript有効時のランディングページ冒頭コピーを価値先行の具体文へ変更する。
- `frontend/index.html`: JavaScriptなしで読まれるプリレンダー済み冒頭コピーを同じ内容へ変更する。
- `scripts/prerender.py`: 次回プリレンダー時にも同じ冒頭コピーが生成されるように変更する。

## 文書

- `README.md`: lane 表記と冒頭の製品説明を公式表記・価値先行コピーへ統一する。
- `docs/SUBMISSION.md`: `#startup`、Startup lane、審査向けの冒頭説明へ変更する。
- `docs/BUILDER_CENTER_BODY.md`: 3,000文字制限内の提出本文でタグ・lane・冒頭説明を変更する。
- `docs/BUILDER_CENTER_POST.md`: 詳細版のタグ・lane・冒頭説明を変更する。
- `tasks/phase1-step8.md`: 検証後の差分要約を記録する。

## テスト

- 変更なし。`backend/tests/test_consistency.py` の既存テストを回帰確認に使う。

## 各ファイルの変更理由

- 表示3ファイル: STEP 1の「どの入口でも同じ価値を30秒で伝える」を満たし、動的表示と静的表示の不一致を防ぐ。
- 文書4ファイル: STEP 1の「公式タグへの統一」と「実障害→82%一致→前回の復旧策」を満たす。
- STEP 8記録: phase-gate の完了条件を満たす。

## 変更不要と判断したファイル

- `backend/tests/test_consistency.py`: DOM構造と主要な既存語句を維持するため、期待値変更は不要。
- `frontend/styles.css`: レイアウト・装飾は変更しない。
- `backend/`: API、データ、分析ロジックは変更しない。
- `infra/`: デプロイ構成とAWSリソースは変更しない。
- `docs/ARCHITECTURE.md`, `docs/SIMILARITY.md`, `docs/DEPLOYMENT.md`: laneタグや審査用冒頭コピーを持たず、技術正本の変更は不要。
- `docs/evidence/`: 過去の実行記録であり、書き換えない。

## 変更順序

1. READMEと提出文書のタグ・冒頭コピーを統一する。
2. JavaScript版、プリレンダー生成元、現在の静的HTMLを同じコピーへ変更する。
3. タグ検索、テスト、ブラウザ確認を実施する。
4. STEP 8の差分要約を作成する。
