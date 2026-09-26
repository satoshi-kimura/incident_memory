**Live app (no login):** https://d2zs12dmk7373h.cloudfront.net
**Evidence:** https://d2zs12dmk7373h.cloudfront.net/evidence.html
**Category:** Commercial potential · **Track:** Startup

> Incident Memory turns an AWS alarm into an answer: what changed, which past failure matches, and what worked last time.

### Problem
Monitoring says something is wrong. The expensive part comes next: reconstructing what changed, finding a similar
past failure and recovering the resolution buried in someone's head, a chat thread or an old postmortem.

### What it does
It collects CloudWatch and CloudTrail evidence around an alarm, rebuilds a timeline with evidence IDs, stores a structured memory in DynamoDB and compares it with past incidents.

In the featured demo, real CloudWatch and CloudTrail evidence reconstructs a Lambda configuration change followed by
errors → latency → concurrency → alarm. Incident Memory finds a clearly labeled seeded incident, INC-0012, at **82%**:
a different cause (a DB connection pool change) with the same degradation sequence. It explains the match and surfaces
the previous rollback and **14-minute recovery** before the on-call engineer repeats the investigation.

Real data too: a sanitized production DB alarm recurred 27 times in 6 days. With no recorded cause or fix, the app says "Insufficient evidence" / "No resolution recorded".

Monitoring shows what is happening now. Incident Memory remembers what worked last time: long-term memory, beyond the 7–90 days CloudWatch investigations keeps.

### How it works
- CloudFront, S3, API Gateway, Lambda, DynamoDB, CloudWatch, CloudTrail, Bedrock (Nova 2 Lite)
- Similarity is deterministic (5 documented factors). AI never sets the score.
- Bedrock explains; every cause must cite evidence IDs, else "Insufficient evidence".
- Read-only AWS workload access, least-privilege IAM, isolated demo environment.

### How the coding agent helped
Claude Code connected to AWS through the Agent Toolkit for AWS, using a dedicated IAM user.
- I wrote the spec and safety rules; the agent built the app, tests and Terraform, with a plan gate blocking changes outside the project.
- I rejected a 96% match as "looks staged"; the agent reworked the demo into a different-cause story (82%).
- It ran real incidents in AWS, verified the live URL and fixed its own bugs; I approved infra changes.

Proof (evidence link): the /mcp panel shows aws-mcp connected; the agent called aws___run_script read-only; CloudTrail logged the calls from aws-mcp.amazonaws.com.

### Why a business
Built by Satoshi Kimura, founder of ENOXA. Running Gatepath on AWS, I kept re-investigating the same alarms. Next: read-only cross-account onboarding, automatic memories and team insights. Incident Memory is standalone and reads no Gatepath data.

Labels: LIVE/CAPTURED DEMO = real AWS evidence from an isolated demo; CAPTURED REAL-WORLD = sanitized production data; SEEDED = fictional.

#commercial-potential #startups
