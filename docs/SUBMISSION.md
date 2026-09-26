# AWS Zero to Shipped — Submission Draft

Draft text for the AWS Builder Center project page. Everything below is in English and
consistent with the product story.

- **Project name:** Incident Memory
- **Tagline:** Your infrastructure remembers what happened last time.
- **Live app:** https://d2zs12dmk7373h.cloudfront.net
- **Category tag:** `#commercial-potential`
- **Lane tag:** `#startups`

---

## Story

Monitoring tools tell engineers that something is wrong.

Engineers then spend time reconstructing what changed, what happened previously, and
whether the team has already solved the same problem.

**Incident Memory converts operational events into reusable organizational memory.**

When a new incident occurs, it does not only analyze what is happening now. It asks:
**Have we seen this pattern before, and what happened last time?**

## What it does

1. Open an alarm-triggered incident and click **Analyze Incident**.
2. Incident Memory collects bounded evidence from **Amazon CloudWatch** (alarm state,
   transitions and metrics) and **AWS CloudTrail** (configuration and deployment events),
   limited to an allowlisted demo workload.
3. It reduces raw data to a timeline and structured signals, each with an evidence ID
   (`CT-001`, `CW-002`, …), and stores the incident as a structured **Incident Memory** in **Amazon DynamoDB**.
4. It compares the new incident with resolved incidents using a **deterministic similarity score**
   built from five documented factors: alarm signature, resource type, signal overlap, event sequence
   and preceding change.
5. **Amazon Bedrock** (Amazon Nova 2 Lite through the Converse API; the model is configurable) explains the evidence, suggests evidence-backed suspected causes, and
   explains the similarity. It never calculates the score, and every claim must cite evidence.
6. The UI shows the closest past pattern and why it matched. For example, "82% similar to INC-0012", from ten weeks
   earlier: a **database connection pool change**, not a Lambda configuration change. It had the same latency alarm and
   the same degradation sequence (configuration change → errors ↑ → latency ↑ → concurrency ↑ → alarm), but different
   resources. "Last time, the errors alarm fired 3 minutes after the latency alarm. Reverting the pool change
   recovered the service 14 minutes after the alarm."

The value is not finding an identical failure. It is recognizing a **similar operational pattern** across
different causes and resources, and saying precisely where the two incidents match and where they differ.

### How is this different from CloudWatch investigations?

Amazon CloudWatch investigations helps you investigate what is happening now: it correlates metrics, logs,
deployments and CloudTrail changes and suggests hypotheses. Its data is kept for 7 to 90 days, and AWS recommends
copying important incident reports elsewhere to keep them longer
([CloudWatch investigations data retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-Retention.html)).

Incident Memory is that "elsewhere", and more: **long-term operational memory**. Every incident is kept as a
structured memory (trigger, timeline, signals, changes, cause, resolution, pattern). When a similar pattern returns,
even with a different cause, Incident Memory shows why it matches, what is different, and **what the team did
last time and how long recovery took**.

> Cloud monitoring helps you investigate what is happening now. Incident Memory remembers what your team learned last time.

## Why it matters (Startups lane)

Every on-call team repeats investigations it has already done. Postmortems are written
once and rarely consulted during the next incident. Incident Memory makes past incidents
queryable at the moment they matter: structured, comparable and evidence-backed.

**Who is building it:** Incident Memory is built by **ENOXA**, the team behind **[Gatepath](https://gatepath.jp)**, a permission-aware
enterprise knowledge search across Slack, Google Drive, Microsoft 365, Confluence, Jira, GitHub and more.
Running Gatepath on AWS, we kept re-investigating the same alarm patterns, and that is why we built Incident Memory.
Incident Memory is a standalone product: it does not connect to Gatepath or read any Gatepath data.

**Where it is headed**

- Cross-account onboarding with a read-only IAM role (STS AssumeRole, external ID)
- Automatic memory creation for every alarm, and resolution capture from runbooks and tickets
- Team-level memory: "3 of the last 5 incidents after config changes to this service were fixed by rollback"
- Integrations where engineers already work (chat, paging) once the core memory is proven

**First users:** small SaaS teams on AWS without a dedicated SRE function, where incident
knowledge lives in one or two people's heads.

## How it was built

- **Coding agent:** Claude Code (Anthropic), connected to the AWS account through the **Agent Toolkit for AWS**
  (AWS MCP Server + AWS skills). Proof: [evidence/AWS_CONNECTION.md](evidence/AWS_CONNECTION.md). It designed the
  data model and similarity algorithm, wrote the backend, frontend and Terraform, ran the
  Terraform plan and inspected it for changes to unrelated resources, deployed, ran the
  controlled incident scenarios, and captured evidence.
  See [evidence/DEVELOPMENT_LOG.md](evidence/DEVELOPMENT_LOG.md).
- **AWS services:** CloudFront, S3, API Gateway (HTTP API), Lambda, DynamoDB, CloudWatch
  (alarms, metrics, logs), CloudTrail (event history), Amazon Bedrock, EventBridge, IAM.
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md), diagram [architecture.png](architecture.png).

### Who did what: human decisions, agent execution

The builder acted as product owner and reviewer. The coding agent did the implementation and operations work.
The decisions that shaped the product were made by the builder:

| Builder decided or reviewed | Agent executed |
|---|---|
| **Product concept and scope.** Wrote the specification (v1, then v2): the Incident Memory model, five similarity factors and weights, a 60 % threshold, evidence IDs, and what is out of scope | Data model, collectors, signal detection, similarity algorithm, API, UI, 28 tests |
| **Safety boundary.** Deploy into an existing AWS account that also runs a production workload, but strictly isolated: own prefix, tags, IAM user, Terraform state, and a plan gate that stops on any change outside the project | Terraform for about 40 resources, the plan safety gate (`scripts/check_plan.py`), least-privilege IAM |
| **The core demo message.** Rejected a 96 % match against a near-identical incident as "looks staged". Asked for a *different cause with a similar degradation pattern* at about 80 %, plus "why similar", "what is different" and "what happened last time" | Reworked the demo workload and history. The unchanged algorithm now scores 82 %. New UI sections |
| **Data consistency review.** Asked that Started always mean the alarm time, that OPEN not carry an end time, that evidence IDs follow time order, and that alarms agree with thresholds, each backed by automated tests | Fixes plus `tests/test_consistency.py` |
| **No production data.** Chose to build comparison incidents in the isolated demo environment instead of sanitizing real production incidents; all demo data is labeled | Controlled incident runs with real CloudWatch and CloudTrail evidence; seeded history labeled fictional |
| **Infrastructure changes approved.** Authorized the initial deployment; for later changes, read the plan summary and approved each `terraform apply` | Planned, ran the plan gate, applied, verified on the public URL |
| **Agent connection.** Connected the coding agent to AWS with the Agent Toolkit for AWS, through a dedicated IAM user limited to the project's resources | Used the AWS MCP Server for AWS operations |

The agent also found and fixed its own mistakes during verification (a demo escalation bug, an earlier episode
leaking into a timeline, over-confident AI wording). The builder decided when the result was good enough to ship.

## Responsible AI and safety

- The public app is read-only toward AWS resources. It performs no remediation and no configuration changes.
- Judges never enter AWS credentials. The backend uses a least-privilege IAM role plus an application allowlist.
- The browser can only reference predefined incident IDs. There are no free-form prompts, ARNs or queries.
- Similarity scores are deterministic. AI output is validated against evidence IDs.
  *Insufficient evidence* is shown instead of guessing.
- Bedrock calls are cached by evidence fingerprint and capped per day.

## Honest labeling of demo data

- `LIVE_DEMO`: collected from AWS for a controlled demo workload. The Lambda function simulates a
  downstream database. The configuration change, Lambda metrics and alarms are real AWS events.
- `CAPTURED_DEMO`: captured from a controlled incident in the same demo environment. The capture pipeline was
  proven with a real run (`evidence/captured-demo-run-2026-09-25.json`). It is not in the comparison set, because an
  identical incident from 41 minutes earlier would not show pattern recognition.
- `SEEDED_DEMO`: fictional historical incidents, clearly labeled, never presented as real production incidents.

## Checklist before submitting

- [ ] Live URL reachable from a clean browser (no login)
- [x] Proof of coding-agent connection to AWS documented: evidence/AWS_CONNECTION.md (MCP config, tool list, read-only call, CloudTrail events)
- [x] Screenshots of the agent calling aws-mcp (evidence/screenshots/05-agent-calling-aws-mcp.png, 06-agent-called-aws-mcp.png) and the `/mcp` panel (07-claude-code-mcp-aws-connected.png)
- [x] Screenshots captured (docs/evidence/screenshots): attach them to the Builder Center page
- [x] Architecture diagram ready (docs/architecture.png): attach it to the Builder Center page
- [ ] Tags: `#commercial-potential`, `#startups`
- [ ] Development process and coding-agent usage described
