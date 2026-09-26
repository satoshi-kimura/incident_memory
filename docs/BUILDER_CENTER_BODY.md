**Live app (no login):** https://d2zs12dmk7373h.cloudfront.net
**Category:** Commercial potential · **Track:** Startups

> A new AWS incident occurs. Incident Memory reconstructs what happened, recognizes a similar past failure pattern, and shows what worked last time.

### Problem
Monitoring says something is wrong. Engineers then ask "have we seen this before?" The answer sits in someone's head or a lost postmortem.

### What it does
It collects CloudWatch and CloudTrail evidence around an alarm, rebuilds a timeline with evidence IDs, stores a structured memory in DynamoDB, and compares it with past incidents.

In the demo, a real Lambda config change causes errors → latency → alarm. Incident Memory finds a seeded historical scenario, INC-0012, at 82%: a different cause (a DB connection pool change) with the same degradation sequence. It shows why it matches, what differs, and how the previous resolution would be reused.

Monitoring shows what is happening now. Incident Memory remembers what worked last time: long-term memory, beyond the 7–90 days CloudWatch investigations keeps.

[image: incident analysis]

### How it works
- AWS: CloudFront, S3, API Gateway, Lambda, DynamoDB, CloudWatch, CloudTrail, Amazon Bedrock (Nova 2 Lite)
- Similarity is deterministic (5 documented factors). AI never sets the score.
- Bedrock explains; every cause must cite evidence IDs, else "Insufficient evidence".
- Read-only AWS workload access, least-privilege IAM, isolated demo environment.

[image: architecture]

### How the coding agent helped
Claude Code, connected to AWS via the Agent Toolkit for AWS (AWS MCP Server), with a dedicated IAM user.
- I wrote the spec and safety rules; the agent built the app, 31 tests and Terraform (~40 resources) with a plan gate that blocks changes outside the project.
- I rejected a 96% match as "looks staged"; the agent reworked the demo into a different-cause story (82%).
- The agent ran real incidents in AWS, verified the live URL and fixed its own bugs. I approved infrastructure changes.

Proof: /mcp panel, the agent calling aws___run_script, CloudTrail events from aws-mcp.amazonaws.com.

[image: /mcp panel] [image: agent calling AWS MCP]

### Why a business
Built by Satoshi Kimura, founder of ENOXA, the company behind Gatepath (gatepath.jp). Running Gatepath on AWS, I kept re-investigating the same alarms. Next: read-only cross-account onboarding, a memory for every alarm, team insights. Standalone; no Gatepath data.

LIVE/CAPTURED incidents use real AWS evidence from an isolated demo; SEEDED ones are fictional and labeled.

#commercial-potential #startups
