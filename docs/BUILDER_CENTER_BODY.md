**Live app:** [https://d2zs12dmk7373h.cloudfront.net](https://d2zs12dmk7373h.cloudfront.net)
**Evidence:** [https://d2zs12dmk7373h.cloudfront.net/evidence.html](https://d2zs12dmk7373h.cloudfront.net/evidence.html)
**Category:** Commercial potential · **Track:** Startup

### Problem

Monitoring tells you something is wrong. The costly part comes next: reconstructing what changed, finding a similar past failure, and recovering the resolution buried in someone’s head, chat history, or an old postmortem.

### What it does

Incident Memory collects CloudWatch and CloudTrail evidence around an alarm, reconstructs a timeline, stores the incident as structured memory in DynamoDB, and compares it with past incidents.

In the featured demo, real AWS evidence reconstructs a Lambda configuration change followed by **errors → latency → concurrency → alarm**. Incident Memory finds seeded incident INC-0012 at **82% similarity**. Its cause is different—a DB connection pool change—but the degradation pattern is similar. The app explains why they match and shows what happened last time: the suspected cause, rollback, and **14-minute recovery**.

It also shows exact recurrence with sanitized production data: the same database free-memory alarm recurred **27 times over five days**. With no confirmed cause or fix in the source data, the app reports **“Insufficient evidence”** and **“No resolution recorded.”**

**Monitoring shows what is happening now. Incident Memory remembers what worked last time.**

### How it works

* AWS: CloudFront, S3, API Gateway, Lambda, DynamoDB, CloudWatch, CloudTrail, Bedrock (Nova 2 Lite)
* Similarity is deterministic across five factors; AI never sets the score.
* Bedrock explains results; suspected causes must cite evidence IDs.
* AWS workload access is read-only with least-privilege IAM.

### How the coding agent helped

Claude Code connected to AWS through the Agent Toolkit for AWS.

* I wrote the specification and safety rules; the agent built the app, tests, and Terraform.
* I rejected an initial **96% match** because it looked staged; the agent reworked it into an explainable **82% different-cause match**.
* The agent created controlled AWS incidents, verified deployment, and fixed implementation issues. I approved infrastructure changes.

**Proof:** the evidence page shows `/mcp` with `aws-mcp` connected, read-only `aws___run_script` calls, and CloudTrail events from `aws-mcp.amazonaws.com`.

### Commercial potential

I built Incident Memory after repeatedly investigating the same alarms while operating Gatepath on AWS. Next: read-only cross-account onboarding, automatic incident memories, and team insights.

Incident Memory is standalone and does not read Gatepath data.

\#commercial-potential #startups
