# Incident Memory

**Your infrastructure remembers what happened last time.**

Live demo: **https://d2zs12dmk7373h.cloudfront.net** (no login, no AWS credentials)

AWS Zero to Shipped Hackathon · Category: **Commercial potential** · Lane: **Startups**

---

## The problem

Monitoring tools tell engineers that something is wrong. The engineers then spend time
reconstructing what changed, what happened previously, and whether the team has already
solved the same problem. That knowledge usually lives in someone's head, a chat
thread, or a postmortem nobody can find at 2 a.m.

## The solution

Incident Memory turns operational events into reusable organizational memory.

When a new AWS incident occurs, it:

1. collects bounded **CloudWatch** and **CloudTrail** evidence around the alarm,
2. reconstructs a **timeline** and structured **signals** (every item has an evidence ID such as `CT-001`, `CW-002`),
3. stores the incident as a structured **Incident Memory** in DynamoDB,
4. compares it with previous incidents using a **deterministic, explainable similarity score**, and
5. explains, with **Amazon Bedrock**, what is similar, what the suspected cause was last time,
   what the team did, and how long recovery took.

It does not only analyze what is happening now. It asks:
**Have we seen this pattern before, and what happened last time?**

> **80% similar to INC-0012** (ten weeks earlier). The direct cause was different (a database parameter
> change instead of a Lambda configuration change), but the degradation followed the same sequence:
> change → duration ↑ → concurrency ↑ → latency alarm. **Last time, errors started 4 minutes after the
> latency alarm.** The team reverted the change and recovered 14 minutes after the alarm.

The point is not to find an identical failure. It is to recognize a **similar operational pattern**
across different resources and causes, and to explain exactly why it matched and where it differs.

## What makes it different

- **Memory, not a log summarizer.** Incidents are stored as structured data (trigger, timeline,
  signals, changes, causes, resolution, normalized pattern) and can be compared later.
- **Explainable scores.** Similarity comes from five documented factors ([docs/SIMILARITY.md](docs/SIMILARITY.md)).
  The AI explains the score but never produces it.
- **Evidence-grounded AI.** Every suspected cause cites evidence IDs. Unsupported claims are
  dropped, and *Insufficient evidence* is a valid answer.
- **Read-only and isolated.** Two layers: least-privilege IAM plus an application allowlist.
  No remediation and no AWS changes from the public app.
- **Costs nothing when idle.** Serverless only. Bedrock results are cached by evidence fingerprint and capped per day.

## Try the demo (60 seconds)

1. Open the live URL.
2. Under **Current incidents**, open the live demo incident (source `LIVE DEMO`).
3. Click **Analyze Incident**.
4. Read the result:
   - **the match**: "80% similar to INC-0012", **Why 80% similar?** (what matches, what differs), and what happened next last time
   - **Timeline**: CloudTrail change, then Duration increase, then concurrency increase, then alarm
   - **Suspected Causes** with confidence and evidence
   - **Similar Incidents** with the per-factor score breakdown
   - **Previous Resolution** from the historical incident
5. Open **INC-0012** to see the historical memory it matched.

Data sources are labeled in the UI:
`LIVE_DEMO` means collected now from AWS for the demo workload. `CAPTURED_DEMO` means captured
earlier from a controlled demo incident in AWS. `SEEDED_DEMO` means fictional history for
demonstration, never presented as a real production incident.

## Architecture

![Architecture](docs/architecture.png)

CloudFront + S3 → API Gateway (HTTP API) → Lambda (Python) → DynamoDB, with read-only
CloudWatch and CloudTrail access and Amazon Bedrock for explanations. Details:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```
backend/app/        Lambda application (collectors, signals, memory, similarity, AI, API)
backend/tests/      Unit and pipeline tests (python -m unittest)
backend/scripts/    seed.py (SEEDED_DEMO history), capture.py (CAPTURED_DEMO from a real run)
demo/               Demo workload Lambda + controlled incident generator
frontend/           Static UI (no build step)
infra/              Terraform (dedicated state, us-east-1)
docs/               Architecture, similarity, deployment, submission, evidence
```

## Local development

```
cd backend
python3 -m venv ../.venv
../.venv/bin/pip install anthropic boto3
../.venv/bin/python -m unittest discover -s tests
STORE_BACKEND=memory BEDROCK_CLIENT=disabled \
  ../.venv/bin/python local_server.py --fixture
```

`--fixture` uses synthetic collectors for UI work without AWS access. Without the flag,
the server reads the real demo environment with your local AWS profile.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Scope

This is a hackathon MVP. Out of scope: remediation, customer account onboarding,
multi-tenancy, billing, chat, and integrations (Slack, Datadog, GitHub).
