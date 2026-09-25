# Incident Memory

AWS Zero to Shipped Hackathon の MVP。CloudWatch / CloudTrail の証拠から障害を構造化して DynamoDB に保存し、過去の障害との類似度（決定的・説明可能なスコア）を出し、Bedrock で説明する。
構成・類似度・デプロイ手順の正本は [`README.md`](README.md)、[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)、[`docs/SIMILARITY.md`](docs/SIMILARITY.md)、[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。

# AWS アカウントと分離（恒久ルール）

- デプロイ先は他プロジェクトと共用の AWS アカウント（`us-east-1`）。アカウント ID・プロファイル名などの実値は git 管理外の `CLAUDE.local.md` に置く。
- AWS CLI / Terraform / AWS MCP はすべて **専用の AWS プロファイル**（専用 IAM ユーザー）を使う。
  - CLI: `--profile <profile>`
  - Terraform: `AWS_PROFILE=<profile> terraform ...`
  - **root や他の IAM ユーザーの認証情報は使わない。**
- 認証が切れたら `aws login --region us-east-1 --profile <profile>`（ブラウザ認証はユーザーが行う）。
- **すべての AWS リソース名は `incident-memory-` で始める。** 他プロジェクトのリソースは読まない・変更しない。
- 専用ユーザーの権限はカスタマー管理ポリシー `incident-memory-deploy`（`incident-memory-*` のみ、`us-east-1` のみ）。
  AccessDenied が出たら、root や別ユーザーに切り替えず、**必要最小限の追加権限をユーザーに提案する**。
  IAM ユーザーのインラインポリシーは 2,048 文字上限なので、追加は管理ポリシー側に入れる。
- 公開アプリ（Lambda）は読み取り専用。修復や AWS への変更を行うコードを追加しない。

# Terraform（恒久ルール）

- インフラは `infra/` の Terraform で管理する。**CDK / CloudFormation は使わない**（下の AWS Agent Toolkit ルールより優先）。
- State は S3（`incident-memory-tfstate-<ACCOUNT_ID>`, key `incident-memory/terraform.tfstate`）。ローカル state を残さない。
- `terraform init` には必ず `-backend-config=backend.hcl` を付ける（`backend.hcl` は git 管理外。`backend.hcl.example` を参照）。
- 手順は `./scripts/build.sh` → `terraform plan -out=tfplan` → plan を確認 → `terraform apply tfplan`。
  **apply はユーザーの確認を取ってから実行する。**

# テスト実行（恒久ルール）

```
cd backend
../.venv/bin/python -m unittest discover -s tests
```

- AWS なしで UI を確認するときは `STORE_BACKEND=memory BEDROCK_CLIENT=disabled ../.venv/bin/python local_server.py --fixture`。
- テストは仕様書として扱う。テストが通らないときはテストではなく実装を直す。
  テスト自体のバグ、または仕様変更が明示的に承認された場合のみテストを変更してよい。変更前に必ず確認を求める。
- 「テストが通った」「動いた」は実行結果を見てから言う。実行していない検証を完了扱いにしない。

# 依存関係の実在確認（恒久ルール）

新しい依存（pip パッケージ、Terraform provider / module、Bedrock のモデル ID）を追加する前に、**実在とバージョンを確認する**。
うろ覚えの名前を書かない。存在しないパッケージ名は、ビルド失敗だけでなく package poisoning（幻の名前を第三者が先取り登録する攻撃）の入口になる。

# 同一バグ修正の打ち切り条件（恒久ルール）

同じバグ・テスト失敗への修正が **2回失敗したら、3回目を試す前に原因仮説を書き直す**。
それまでに観測した事実（エラーメッセージ・ログ・テスト出力）と、否定された仮説を明記してから再開する。
誤った仮説の上に修正を積み続けない。

# ユーザーへの説明の書き方（恒久ルール）

- 会話は日本語。プロダクト（UI 文言・README・コード・コメント）は英語。
- **1行目に「終わりました」か「まだ終わっていません。いま〜の段階です」を書く。**
- 次に結論を 1〜2 文。変更前 → 変更後を先に示し、なぜ必要かを説明してから実装の詳細に入る。
- 短く書く。調べた事実や変更ファイル一覧を並べない。相手が次に何を判断できるかを優先し、詳細は聞かれてから出す。
- 新しい用語やリソース名を出すときは、役割を一言添える。

# 進め方

- **Simplicity First**: 変更は必要最小限。触る範囲を広げない。
- **No Laziness**: 根本原因を直す。一時しのぎの修正をしない。
- **Verification Before Done**: 動くことを示してから完了にする（テスト、ログ、デプロイ後の URL 確認）。
- 3ステップ以上・設計判断を含む作業は、先に計画を示してから着手する。うまくいかなくなったら押し切らず、止まって計画し直す。

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->
