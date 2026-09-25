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
6. The UI shows the closest past pattern and why it matched. For example, "80% similar to INC-0012", from ten weeks
   earlier: a database parameter change, not a Lambda configuration change. It had the same latency alarm and
   the same degradation sequence (change → duration ↑ → concurrency ↑ → alarm), with different resources.
   "Last time, errors started 4 minutes after the latency alarm; reverting the change recovered the service."

The value is not finding an identical failure. It is recognizing a **similar operational pattern** across
different causes and resources, and saying precisely where the two incidents match and where they differ.

## Why it matters (Startups lane)

Every on-call team repeats investigations it has already done. Postmortems are written
once and rarely consulted during the next incident. Incident Memory makes past incidents
queryable at the moment they matter: structured, comparable and evidence-backed.

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
