# Builder Center post: Incident Memory

Copy the sections below into the AWS Builder Center project page.

- **Title:** Incident Memory: your infrastructure remembers what happened last time
- **Tags:** `#commercial-potential` `#startups`
- **Live app:** https://d2zs12dmk7373h.cloudfront.net
- **Cover image:** `evidence/screenshots/03-incident-analysis-light.png` (crop the top: score, "Why 82% similar?", "What happened last time?")
- **Images in the body:** `architecture.png`, `evidence/screenshots/01-dashboard.png`, `evidence/screenshots/03-incident-analysis-light.png`, `evidence/screenshots/07-claude-code-mcp-aws-connected.png`

---

## Incident Memory: your infrastructure remembers what happened last time

**Live app (no login, no AWS credentials):** https://d2zs12dmk7373h.cloudfront.net
**Category:** Commercial potential · **Lane:** Startups

> A new AWS incident occurs. Incident Memory reconstructs what happened, recognizes a similar historical failure pattern, and shows what worked last time.

### The 2 a.m. problem

Monitoring tells you that something is wrong. Then the real work starts: an on-call engineer reconstructs what
changed, scrolls through dashboards, and asks the team channel "have we seen this before?". Often the team *has*
seen it before. The answer is in someone's head, an old chat thread, or a postmortem nobody can find at 2 a.m.

We run a SaaS product on AWS, and we kept re-investigating the same alarm patterns. So we built the tool we wanted.

### What Incident Memory does

Incident Memory turns every AWS incident into a **structured memory**, then compares new incidents with
what happened last time.

1. **Collect evidence** from Amazon CloudWatch (alarm state, transitions, metrics) and AWS CloudTrail
   (configuration and deployment changes), in a bounded window around the alarm.
2. **Reconstruct the incident**: a timeline and structured signals, each with an evidence ID (`CT-001`, `CW-002`).
3. **Store it** as an Incident Memory in Amazon DynamoDB: trigger, timeline, signals, changes, suspected causes,
   resolution, and a normalized pattern.
4. **Compare** it with past incidents using a **deterministic, explainable similarity score**.
5. **Explain** with Amazon Bedrock what matches, what differs, and **what happened last time**: the previous
   suspected cause, the action the team took, the outcome, and the time to recovery.

It does not only ask "what is happening now?" It asks **"Have we seen this pattern before, and what happened last time?"**

*[image: 01-dashboard.png]*

### Try it in 60 seconds

Open the live app, then open the current incident *Orders API latency after Lambda configuration change*.

- A Lambda configuration change (a shorter downstream timeout plus retries) was followed by **errors ↑, latency ↑,
  concurrency ↑**, and then the latency alarm. This is real CloudTrail and CloudWatch evidence from an isolated
  demo workload.
- Incident Memory finds **INC-0012 at 82 %**. INC-0012 had a **different cause**, a database connection pool change
  ten weeks earlier, but it degraded in the **same sequence**.
- **Why 82 % similar?** Same latency alarm, same event ordering (5 of 5 events), and a configuration change came
  first in both. It is only a partial match on signals and resources.
- **What is different?** A different change target (the Lambda configuration here, a database connection pool
  there), and database signals that appeared only last time.
- **What happened last time?** The errors alarm fired 3 minutes after the latency alarm. The team reverted the
  pool change and recovered 14 minutes after the alarm.

This is the point of the product. It does not look for an identical failure. It recognizes a **similar operational
pattern across different causes**, and it reuses what the team learned.

*[image: 03-incident-analysis-light.png]*

### How is this different from CloudWatch investigations?

Amazon CloudWatch investigations helps you investigate what is happening now: it correlates metrics, logs,
deployments and CloudTrail changes and suggests hypotheses. Its data is kept for 7 to 90 days, and AWS recommends
copying important incident reports elsewhere to keep them longer
([CloudWatch investigations data retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-Retention.html)).

Incident Memory is that "elsewhere", and more: **long-term operational memory**. Every incident is kept as a
structured memory (trigger, timeline, signals, changes, cause, resolution, pattern). When a similar pattern returns,
even with a different cause, Incident Memory shows why it matches, what is different, and **what the team did
last time and how long recovery took**.

> Monitoring helps you understand what is happening now. Incident Memory remembers what worked last time.

### How it works

*[image: architecture.png]*

- **Serverless, us-east-1:** CloudFront + S3 (UI), API Gateway HTTP API, AWS Lambda (Python), Amazon DynamoDB,
  Amazon CloudWatch, AWS CloudTrail, Amazon Bedrock. There is no always-on compute, and idle cost is effectively zero.
- **The score is math, not AI.** Five documented factors: alarm signature 25, service and resource type 20,
  signal overlap 25, event sequence 20, preceding change 10. Factors that cannot be calculated are excluded and
  the score is re-normalized. The UI shows every factor with its reason.
- **AI explains, and evidence decides.** Bedrock receives only normalized evidence. Every suspected cause must cite
  evidence IDs. Unknown IDs, invented percentages and unsupported causes are dropped. *Insufficient evidence* is a
  valid answer. Results are cached by an evidence fingerprint, so repeated clicks never pay twice.
- **Read-only and isolated.** Judges never enter credentials. The browser can only reference incident IDs, never
  ARNs, queries or prompts. IAM is least-privilege, and an application allowlist re-filters every CloudWatch and
  CloudTrail result before it is stored, shown or sent to the model. There is no remediation feature.

### How the coding agent helped us ship

We built Incident Memory with **Claude Code**, connected to our AWS account through the **Agent Toolkit for AWS**
(AWS MCP Server and AWS skills), using a dedicated IAM user limited to the project's resources.

**We decided, the agent executed.**

- **We** wrote the specification: the Incident Memory model, the five similarity factors and a 60 % threshold.
  **The agent** built the data model, collectors, similarity engine, API, UI and 28 tests.
- **We** set the safety boundary: an AWS account that also runs production, so everything had to be isolated.
  **The agent** wrote Terraform for about 40 resources and a *plan gate* that refuses any change outside the
  project. The gate once stopped an apply on a false alarm, which is what it should do when unsure.
- **We** reviewed the first demo and said a 96 % match against a near-identical incident "looks staged".
  **The agent** reworked the demo into a different-cause, similar-pattern story, and the unchanged algorithm scored it 82 %.
- **We** asked for data consistency: Started always means the alarm time, evidence IDs follow time order, and
  alarms agree with thresholds. **The agent** fixed each rule and added automated tests.
- **The agent** ran controlled incidents in AWS, verified every result on the public URL, and found and fixed its
  own bugs along the way. For example, a demo run fired an alarm it should not have, so it found the cause, fixed
  it, and ran the incident again.
- Every `terraform apply` went through the plan gate. For the later changes, **we** read the plan summary and
  approved each apply.

Proof of the AWS connection: the `/mcp` panel showing the AWS MCP Server connected, the agent calling
`aws___run_script`, and CloudTrail events from `aws-mcp.amazonaws.com` recorded by AWS itself.

*[image: 07-claude-code-mcp-aws-connected.png]*

### Why this can be a business (Startups lane)

Every on-call team repeats investigations it has already done. Incident Memory makes past incidents queryable at
the moment they matter: structured, comparable and backed by evidence.

**Who is building it:** ENOXA, the team behind [Gatepath](https://gatepath.jp), a permission-aware enterprise
knowledge search across Slack, Google Drive, Microsoft 365, Confluence, Jira, GitHub and more. Incident Memory is a
standalone product; it does not connect to Gatepath or read any Gatepath data.

**Where it is headed**

- Customer onboarding through a read-only cross-account IAM role (STS AssumeRole with an external ID)
- A memory for every alarm, with resolutions captured from runbooks and tickets
- Team-level insight, for example: "3 of the last 5 incidents after configuration changes to this service were fixed by rollback"
- Answers where engineers already work, in chat and paging tools

**First users:** small SaaS teams on AWS without a dedicated SRE function, where incident knowledge lives in
one or two people's heads.

### Honest notes

- **LIVE DEMO** incidents are collected now from an isolated AWS demo environment; once they recover, their real
  evidence is kept as **CAPTURED DEMO**. **SEEDED DEMO** incidents are
  fictional history created for comparison and are labeled as such. No incident comes from a production system.
- Explanations currently use **Amazon Nova 2 Lite** on Bedrock. The model is a configuration value.
- The similarity score is a historical comparison, not a prediction.

**Try it:** https://d2zs12dmk7373h.cloudfront.net
