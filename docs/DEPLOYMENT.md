# Deployment

**Current deployment:** https://d2zs12dmk7373h.cloudfront.net (`app_url` output of `terraform output`)

Everything deploys to **us-east-1** with Terraform. The Terraform state is dedicated to
Incident Memory (`s3://incident-memory-tfstate-<account>`), separate from any other
project's state.

## Prerequisites

- AWS CLI v2 with credentials for the target account
- Terraform ≥ 1.6, Python 3.13, `zip`
- Amazon Bedrock access to an Anthropic Claude model in us-east-1 (see *Bedrock model* below)

## 1. State bucket (once)

```
ACCOUNT=$(aws sts get-caller-identity \
  --query Account --output text)
aws s3api create-bucket \
  --bucket incident-memory-tfstate-$ACCOUNT \
  --region us-east-1
aws s3api put-bucket-versioning \
  --bucket incident-memory-tfstate-$ACCOUNT \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block \
  --bucket incident-memory-tfstate-$ACCOUNT \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

`infra/backend.hcl` points at this bucket.

## 2. Build Lambda packages

```
./scripts/build.sh
```

This builds `.build/api.zip` (application + Anthropic SDK for arm64) and the two demo function zips.

## 3. Plan, inspect, apply

```
cd infra
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform show -json tfplan | python3 ../scripts/check_plan.py
terraform apply tfplan
```

`scripts/check_plan.py` fails if the plan contains any update, replacement or deletion of
a resource whose name does not start with `incident-memory`, or any reference to other
projects. **If it fails, do not apply.**

## 4. Seed the historical memories

```
cd backend
TABLE_NAME=incident-memory-incidents AWS_REGION=us-east-1 \
  ../.venv/bin/python -m scripts.seed
```

`--skip <ID>` keeps an existing memory with the same ID (for example, a captured one).

## 5. Generate demo incidents

The scenario function is the only component that changes AWS resources. It is not public.

```
aws lambda invoke --region us-east-1 \
  --function-name incident-memory-demo-scenario \
  --invocation-type Event \
  --cli-binary-format raw-in-base64-out \
  --payload '{"mode":"partial"}' /dev/null
```

- `partial` (about 32 minutes): a release raises `DB_POOL_SIZE`, duration and concurrency rise,
  and the latency alarm fires. The configuration is restored after the analysis window has passed.
  This is the live incident judges analyze. A weekly EventBridge rule (Mondays 03:00 UTC) repeats it,
  because 1-minute Lambda metrics are retained for 15 days.
- `full` (about 30 minutes): the same, but errors begin and the release is rolled back. Capture it as
  historical memory:

```
cd backend
TABLE_NAME=incident-memory-incidents AWS_REGION=us-east-1 \
  ../.venv/bin/python -m scripts.capture \
  --episode INC-YYYYMMDD-HHMM --as-id INC-0012 \
  --title "..." --summary "..." --action "..." --result "..." \
  --cause "description|CT-001,CW-001|HIGH"
```

## Bedrock model

The model is configurable without code changes:

| Variable | Default | Notes |
|---|---|---|
| `bedrock_client` | `converse` | `converse` = Bedrock Converse API (any text model), `mantle` = Claude through the Messages API endpoint, `invoke` = Claude through InvokeModel, `disabled` = rule-based only |
| `bedrock_model_id` | `us.amazon.nova-2-lite-v1:0` | For Claude: `anthropic.claude-opus-5` with `mantle`, or a Claude inference profile with `invoke`/`converse` |
| `bedrock_daily_call_limit` | `100` | Cache misses per UTC day |

The deployment uses Amazon Nova 2 Lite, which was accessible without extra onboarding.
Anthropic models on Bedrock require the one-time *Anthropic use case details* form in the
Bedrock console. After it is approved, switch without code changes:

```
cd infra
terraform plan -out=tfplan \
  -var bedrock_client=mantle \
  -var bedrock_model_id=anthropic.claude-opus-5
```

The evidence fingerprint includes the model ID, so new analyses are generated with the new model.

## Import captured real-world data (optional)

A production alarm history exported by the operator (DescribeAlarmHistory JSON plus GetMetricStatistics JSON
for the alarm's metric) can be imported as sanitized `CAPTURED_REAL_WORLD` memories, one per ALARM → OK cycle.
The raw files stay outside the repository; only the sanitized result is stored.

```
cd backend
TABLE_NAME=incident-memory-incidents AWS_REGION=us-east-1 \
  ../.venv/bin/python -m scripts.import_real_world \
  --history /path/to/alarm-history.json \
  --datapoints /path/to/datapoints.json
```

The importer refuses to store anything that still contains an account ID, ARN or source-system name.

## Prerender the landing page

The landing page contains a static, JavaScript-free version of the featured analysis, so crawlers and AI scoring
systems can read it. After the live incident is analyzed, refresh it from the public API and deploy:

```
python3 scripts/prerender.py
./scripts/build.sh
```

## Update the frontend or backend

Re-run `./scripts/build.sh`, then plan, inspect and apply. Terraform uploads changed files to
S3. CloudFront caches static files for up to 5 minutes, and `index.html` is not cached.

## Tear down

```
cd infra
terraform destroy
```

The state bucket is kept. Delete it manually if you no longer need it.
