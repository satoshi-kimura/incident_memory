# Phase2 編集対象ファイル

## 本体実装・表示

- `frontend/app.js`
  - dashboardをfeatured incident中心の階層へ変更する。
  - real-world cycles、incident memory、source legendを展開可能な補助領域へ整理する。
  - analysis結果の一次情報と詳細情報を分離する。
  - evidence chipが入れ子のdetailsも開けるよう、既存ジャンプ処理を維持・補強する。
- `frontend/styles.css`
  - featured card、CTA、metric summary、details group、mobile card layoutを追加する。
  - 既存のdark mode、reduced motion、tables、charts、tooltipsを維持する。
- `scripts/prerender.py`
  - JavaScriptなしでも同じ情報優先順位になるよう、featured cardと展開可能な補助領域を生成する。
- `frontend/index.html`
  - 現在のプリレンダー済みHTMLを新構造に同期する。
- `tasks/phase2-step8.md`
  - 検証後の差分要約を保存する。

## テスト

- 変更なし。`backend/tests/test_consistency.py` を含む既存テストを回帰確認に使用する。

## 各ファイルの変更理由

- `frontend/app.js`: STEP 1のprogressive disclosureと全操作維持の本体。
- `frontend/styles.css`: 視覚的優先順位とdesktop/mobileの簡潔なレイアウトを実現する。
- `scripts/prerender.py`, `frontend/index.html`: AI scoring systemとJavaScript無効環境でも主要内容を削らず、構造を一致させる。
- `tasks/phase2-step8.md`: phase-gate完了条件。

## 変更不要と判断したファイル

- `backend/`: API・データ・分析機能は変更しない。
- `backend/tests/`: 既存仕様と主要静的コンテンツの保証を弱めない。ユーザー承認なしに変更しない。
- `infra/`: AWS構成とデプロイ方法は変更しない。
- `README.md`, `docs/`: 製品説明はPhase1で整理済み。今回は画面構造だけを対象にする。
- `demo/`: fixtureとデモデータは変更しない。

## 変更順序

1. `frontend/app.js`でdashboard/detailの情報階層を変更する。
2. `frontend/styles.css`で新しい構造をdesktop/mobile対応する。
3. `scripts/prerender.py`と`frontend/index.html`を同じ階層へ同期する。
4. 構文、43テスト、ブラウザ操作、console/API logを検証する。
5. `tasks/phase2-step8.md`を作成する。
