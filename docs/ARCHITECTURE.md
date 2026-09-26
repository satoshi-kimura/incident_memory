# Architecture

**Live app:** https://d2zs12dmk7373h.cloudfront.net (CloudFront → S3 + API Gateway → Lambda, us-east-1)

![Architecture](architecture.png)

Incident Memory is a small serverless application in **us-east-1** (CloudFront is global).
It has no always-on compute: no EC2, ECS, RDS, OpenSearch or NAT Gateway.

## Components

| Layer | Service | Resource | Purpose |
|---|---|---|---|
| Frontend | Amazon S3 + CloudFront | `incident-memory-web-<account>` (private, OAC) | Static HTML/JS/CSS, public HTTPS URL, security headers |
| API | API Gateway HTTP API | `incident-memory-api` | 4 fixed routes, throttled (5 rps / burst 10; analyze 1 rps / burst 3) |
| Backend | AWS Lambda (Python 3.13, arm64) | `incident-memory-api` | Evidence collection, signal detection, similarity, Bedrock step (async) |
| Storage | Amazon DynamoDB (on-demand) | `incident-memory-incidents` | Incident Memories, cached AI results, daily Bedrock call counter |
| Evidence | Amazon CloudWatch | demo alarms, `AWS/Lambda` metrics | Alarm state, transitions, metric series |
| Evidence | AWS CloudTrail (event history) | demo function only | Configuration and deployment events |
| AI | Amazon Bedrock (Claude) | configurable model ID | Summary, suspected causes, similarity explanations |
| Demo | Lambda + CloudWatch alarms + EventBridge rule | `incident-memory-demo-*` | Controlled demo workload and incident generator |
| Ops | CloudWatch Logs / EMF | `/aws/lambda/incident-memory-api` | App errors, analysis duration, Bedrock and AWS API failures |

All resources are named `incident-memory-*`, tagged `Project=incident-memory`, and
managed by a dedicated Terraform state (`s3://incident-memory-tfstate-<account>`).

## Data sources

| Source type | Where it comes from |
|---|---|
| `LIVE_DEMO` | Collected now from CloudWatch and CloudTrail for the isolated demo workload |
| `CAPTURED_DEMO` | The same evidence, kept as a memory once the incident recovered and its window was complete |
| `CAPTURED_REAL_WORLD` | Imported offline from a production system's exported CloudWatch alarm history and metric datapoints (`backend/scripts/import_real_world.py`), sanitized. One memory per ALARM → OK cycle. The public application never connects to the production system |
| `SEEDED_DEMO` | Fictional incidents created for comparison |

## Public API

| Route | Description |
|---|---|
| `GET /api/incidents` | Stored memories + newly detected demo alarm episodes |
| `GET /api/incidents/{id}` | One incident (used to poll for the AI step) |
| `POST /api/incidents/{id}/analyze` | Analyze a live demo incident |
| `GET /api/health` | Health check |

The browser supplies only an incident ID matching `^INC-(\d{4}|\d{8}-\d{4})$`. It never
supplies ARNs, resource names, metric names, namespaces, regions, time ranges or prompts.

## Analysis pipeline

```
Analyze Incident (INC-20260925-0335)
  │
  ├─ 1. Resolve       ID → demo alarm episode (grouped ALARM transitions of allowlisted alarms)
  ├─ 2. Collect       window = trigger − 30 min … trigger + 15 min
  │     ├─ CloudWatch DescribeAlarms / DescribeAlarmHistory   (exact demo alarm names)
  │     ├─ CloudWatch GetMetricData                            (AWS/Lambda, FunctionName = demo function)
  │     └─ CloudTrail LookupEvents                             (ResourceName = demo function)
  ├─ 3. Filter        discard read-only calls, failed calls, other regions, non-allowlisted resources;
  │                   keep event name, time, resource name and caller type only
  ├─ 4. Reduce        metric series → structured signals (baseline, peak, magnitude, onset, until)
  │                   evidence IDs: CT-001…, CW-001…
  ├─ 5. Memory        timeline + trigger + signals + changes → Incident Memory + normalized pattern
  ├─ 6. Compare       deterministic similarity against RESOLVED memories (threshold 60 %, top 3)
  ├─ 7. Explain       rule-based explanation (always), plus Bedrock (async):
  │                   fingerprint = SHA-256(evidence + matches + model + prompt version)
  │                   cached result → reuse; otherwise one Bedrock call within the daily cap
  └─ 8. Store         DynamoDB; UI polls until the AI step completes

Once an incident has recovered and its full window has been collected, the evidence is final. Re-analysis then
reuses the stored evidence and only repeats the comparison, because 1-minute Lambda metrics expire after 15 days
and re-collecting would lose data. The memory stays intact indefinitely.
```

The Bedrock step runs as an asynchronous self-invocation of the same Lambda
function, because API Gateway requests are capped at 30 seconds. The UI shows the
deterministic results immediately and adds the AI explanation when it arrives.

## Incident Memory

Structured document (see `backend/app/memory.py`):

- **Identity**: ID, title, status (`NEW` not analyzed, `OPEN` alarm active, `RECOVERED` alarms OK but no resolution recorded, `RESOLVED` resolution recorded), created/start/end timestamps,
  region, source type (`LIVE_DEMO`, `CAPTURED_DEMO`, `SEEDED_DEMO`)
- **Started** is always the time the trigger alarm entered ALARM, for live and historical incidents alike.
  Earlier events (such as the configuration change) appear on the timeline at negative offsets (for example −7 min).
- **Evidence IDs** (`CT-001…`, `CW-001…`) are numbered in time order within each incident.
- **Trigger**: alarm name, category (metric family), service, metric, comparison, observed value, threshold, alarm time
- **Timeline**: evidence ID, timestamp, service, category (`change`/`metric`/`alarm`/`recovery`/`action`), description, source
- **Signals**: type, metric, direction, baseline, peak, magnitude, onset/until, evidence IDs
- **Suspected causes**: description, supporting evidence IDs, confidence (`HIGH`/`MEDIUM`/`LOW`), reasoning
- **Resolution**: action, time, result, time to recovery, supporting evidence
- **Pattern**: normalized features for similarity (see [SIMILARITY.md](SIMILARITY.md))

## Similarity

Deterministic and documented in [SIMILARITY.md](SIMILARITY.md). Five weighted factors:
trigger 25, resource type 20, signals 25, sequence 20, preceding change 10.
Unavailable factors are omitted and the score is normalized over the rest.

## Bedrock usage

- **Model (deployed): Amazon Nova 2 Lite** (`us.amazon.nova-2-lite-v1:0`, US cross-region inference
  profile) through the Bedrock **Converse** API. A forced tool call returns JSON that matches the schema.
  This was the most capable text model accessible from us-east-1 in this account at deployment time.
  Anthropic models need the one-time use case form in the Bedrock console, which had not been submitted.
- The model is configurable with Terraform variables, without code changes:
  - `bedrock_client = "converse"` with any Bedrock text model ID or inference profile
  - `bedrock_client = "mantle"` with `bedrock_model_id = "anthropic.claude-opus-5"` (Claude through the Messages API endpoint, native structured outputs)
  - `bedrock_client = "invoke"` with any Claude model or inference profile ID
- Input: normalized evidence only (evidence summaries, signals, timeline, similarity breakdown).
  No raw CloudTrail payloads and no raw metric series.
- Untrusted data: operational text is wrapped in `<incident_data>`, and the system prompt tells
  the model never to follow instructions found inside it.
- Output: a JSON schema (structured outputs), then validation in `backend/app/ai.py`:
  - Suspected causes that cite unknown evidence IDs are dropped.
  - Unknown incident IDs are dropped.
  - Explanations that contain percentages are dropped.
  - If no supported cause remains, the result shows **Insufficient evidence to identify a likely cause**.
- Failure handling: timeout, refusal, invalid output or an exhausted daily cap all fall back to the
  deterministic rule-based explanation, which the UI labels as such.

## IAM and security model

Two layers of isolation:

**Layer 1: IAM (least privilege where AWS supports it)**

| Role | Permissions |
|---|---|
| `incident-memory-api-role` | Its own log group; its own DynamoDB table (Get/Put/Update/Scan); `DescribeAlarms`/`DescribeAlarmHistory` on the 3 demo alarm ARNs; `GetMetricData` and `LookupEvents` (no resource-level support; limited to `us-east-1`); Bedrock inference; async self-invoke |
| `incident-memory-demo-orders-api-role` | Its own log group only |
| `incident-memory-demo-scenario-role` | Invoke and update the configuration of the demo function only; invoke itself |

**Layer 2: application allowlist** (`backend/app/config.py`)

- Alarm queries use exact demo alarm names.
- Metric queries use a fixed namespace, metric names and the `FunctionName` dimension of the demo function.
- CloudTrail lookups use the demo function name. Every returned event is filtered again: all
  referenced resources must be on the allowlist, the region must be us-east-1, the call must be
  a successful write, and it must match a known change category. Anything else is discarded
  before storage, before the browser and before Bedrock.

Other controls:

- The public application writes only its own DynamoDB table and never changes AWS resources.
  There is no remediation feature.
- No AWS credentials exist in the browser, HTML, repository or API responses. The Lambda
  function uses its execution role.
- Evidence keeps no ARNs, account IDs, source IPs or request/response payloads.
- Input validation uses a strict incident ID regex. Unknown routes return 404.
- Errors return generic English messages. Details go to CloudWatch Logs only.
- Controlled incidents are generated only by the separate scenario function. It is not
  reachable from the public API. It runs manually; the optional weekly schedule is disabled during judging
  (`weekly_scenario_enabled = false`), so the verified demo stays fixed.

## Cost controls

| Control | Effect |
|---|---|
| Serverless only | No idle compute cost. DynamoDB on-demand, Lambda and API Gateway pay per request |
| Evidence fingerprint cache | Identical evidence never triggers a second Bedrock call |
| Daily Bedrock cap (default 100 calls) | Atomic DynamoDB counter. Beyond the cap, the rule-based analysis is shown |
| Collection cache (60 s) | Repeated clicks do not repeat AWS API calls |
| API Gateway throttling | 5 rps overall, 1 rps for analyze |
| Log retention | 14 days (demo workload: 3 days) |
| No NAT, VPC, OpenSearch, RDS | No fixed hourly charges |

Expected idle cost is effectively zero, apart from pennies of S3/DynamoDB storage and
CloudWatch alarms (3 standard alarms, about $0.30/month). The optional weekly demo scenario (disabled during judging) runs about 30 Lambda minutes per week of low-memory functions.

**Lambda concurrency.** This account's regional concurrency quota is 10, and AWS
requires at least 10 unreserved, so reserved concurrency cannot be set. Throttling
at API Gateway and the Bedrock cap provide the cost protection instead.

**AWS Budgets.** Not created. The account also hosts other workloads, and no
cost-allocation tag is active yet, so a budget cannot reliably separate Incident Memory
costs. An account-wide budget would misattribute other spending. To enable one later,
activate the `Project` cost-allocation tag in Billing and create a budget filtered on
`user:Project$incident-memory`.

## Future production architecture (not implemented)

Customers would grant a cross-account IAM role (read-only CloudWatch/CloudTrail, external ID).
Incident Memory would use STS AssumeRole per analysis, with a per-tenant resource allowlist and
per-tenant memory partitions. Customer onboarding is out of scope for this MVP.
