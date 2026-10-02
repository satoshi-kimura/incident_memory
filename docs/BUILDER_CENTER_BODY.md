* **Live app:** https://d2zs12dmk7373h.cloudfront.net
* **Evidence:** https://d2zs12dmk7373h.cloudfront.net/evidence.html
* **Category:** Commercial potential · **Track:** Startup

## From an alarm to an answer

Monitoring tells us that something is wrong. The expensive part comes next: reconstructing what changed, finding a similar past failure, and recovering the resolution buried in someone's memory, a chat thread, or an old postmortem.

I built **Incident Memory** to make that process repeatable.

When an AWS alarm occurs, Incident Memory collects evidence from CloudWatch and CloudTrail, reconstructs a timeline, stores the incident as structured memory, and compares it with previous incidents.

The goal is simple:

**What changed? Have we seen this before? What worked last time?**

## How it works

Each event around the alarm gets an evidence ID. The incident record holds the timeline, symptoms, changes, and any resolution.

Past incidents are stored in DynamoDB and compared using five documented similarity factors.

The similarity score is deterministic. AI does not decide the score.

Amazon Bedrock explains the result; its claims must cite evidence IDs.

## Demo

In the demo scenario, Incident Memory reconstructs a sequence involving a Lambda configuration change, errors, increased latency, concurrency changes, and the resulting alarm.

It finds a seeded past incident, **INC-0012**, with an **82% similarity score**, and surfaces the previous rollback and recovery information.

I also tested the model against sanitized operational data from a recurring database memory alarm. That alarm occurred **27 times in five days**, but the historical records contained insufficient evidence and no recorded resolution.

Memory only helps if what happened and what fixed it are preserved. Incident Memory makes that automatic.

## AWS architecture

Amazon CloudFront, S3, API Gateway, Lambda, DynamoDB, CloudWatch, CloudTrail, and Amazon Bedrock (Nova 2 Lite).

AWS access is read-only and designed around least-privilege IAM. The demo environment is isolated from production systems.

Incident Memory is a standalone application and does not read data from Gatepath.

## From zero to shipped

I built it with **Claude Code connected to AWS through the Agent Toolkit for AWS** (AWS MCP Server). I wrote the specification and safety rules; the agent built the app, tests, and Terraform, ran controlled AWS incidents, and verified the deployment. I approved infrastructure changes.

**Proof** (evidence page): `aws-mcp` connected in `/mcp`, read-only `aws___run_script` calls, and CloudTrail events from `aws-mcp.amazonaws.com`.

The focus is the gap **after** monitoring detects a problem: preserving what worked so the next incident starts from the last one.

Next: read-only cross-account onboarding, automatic incident memories, and team insights.

**Built by Satoshi Kimura, founder of ENOXA.**
