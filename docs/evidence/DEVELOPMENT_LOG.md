# Development Log and Coding-Agent Evidence

Built with **Claude Code** (Anthropic's coding agent, CLI), working in the developer's
terminal with access to the AWS account through the AWS CLI and Terraform. Times are UTC.
The account ID is masked as `<ACCOUNT_ID>`.

**Live app:** https://d2zs12dmk7373h.cloudfront.net

## Connection proof

See **[AWS_CONNECTION.md](AWS_CONNECTION.md)**. It covers the Agent Toolkit for AWS (AWS MCP Server +
AWS skills) registered in Claude Code, the tool list, a read-only call through the MCP server
returning this account's Incident Memory resources, and CloudTrail events from
`aws-mcp.amazonaws.com` recorded by AWS.

## Timeline

| Time (UTC) | Step |
|---|---|
| 02:51 | Agent inspected the empty project directory, toolchain and AWS identity. It found that the account also holds another project's Terraform state and asked where to deploy. Decision: same account, strict `incident-memory-` isolation, us-east-1. |
| 02:55 | Probed Amazon Bedrock model access in us-east-1. Anthropic models return 403 until the use-case form is submitted, so the model was made configurable with a rule-based fallback. |
| 03:00 | Implemented the Incident Memory model, SEEDED_DEMO history and the deterministic similarity algorithm, with unit tests. |
| 03:05 | Specification v2 received. Re-planned: five weighted factors, 60 % threshold, CW-/CT- evidence IDs, source types, evidence-fingerprint cache, and a Lambda-based demo workload with real AWS/Lambda metrics. Found the Lambda concurrency quota is 10, so reserved concurrency is impossible; used API Gateway throttling and a Bedrock daily cap instead. No active cost-allocation tags, so no budget; reason documented. |
| 03:10 | Built the collectors (allowlist + re-filtering), analysis pipeline, async Bedrock step, API handler, and pipeline tests (14 passing). |
| 03:12 | Built the frontend and verified it locally against synthetic fixture data (headless Chrome screenshot). |
| 03:17 | Created the dedicated state bucket `incident-memory-tfstate-<ACCOUNT_ID>`. `terraform plan`: 40 to create, 0 to change, 0 to destroy; checked for foreign resources. Applied. |
| 03:20 | Seeded historical memories. Verified the public URL end to end. Started the `full` controlled scenario (real configuration change → degradation → rollback) to capture a CAPTURED_DEMO memory. |
| 03:28 | First full run: the release was applied, but the scenario role lacked `lambda:GetFunction` (required by the update waiter), so the degrade phase did not start. |
| 03:29 | The plan gate refused the next apply: it read an IAM role ARN as a resource name. The gate behaved as designed (stop when unsure). Fixed ARN parsing in `scripts/check_plan.py`. |
| 03:30 | Added the permission. Reset the demo configuration. Re-scheduled the full run with a delayed start, so the aborted change and the reset stay outside the next incident's 30-minute analysis window. Queued the partial (live) run for 04:30. |
| 03:31 | Anthropic models on Bedrock return 403/404 (use-case form not submitted). Tested accessible models and added a model-agnostic Converse client. Deployed Amazon Nova 2 Lite as the explanation model, with the model ID in a Terraform variable. |
| 03:34 | Checked the layout at 390 px width (no page-level horizontal scroll). Code review found that a crashed async AI step could leave `PENDING` forever; added stale-pending recovery and a test for "identical evidence → one Bedrock call". |
| 03:57–04:13 | Full controlled run in AWS: configuration change at 03:56:52 (CloudTrail), Duration ↑ 03:59, ConcurrentExecutions ↑ 04:02, latency alarm 04:04:48, Errors ↑ 04:08, errors alarm 04:09:14, rollback 04:11:24 (CloudTrail), both alarms OK by 04:13:14. |
| 04:15 | Captured the run as **INC-0012 (CAPTURED_DEMO)** with `scripts/capture.py`, replacing the seeded INC-0012. The capture script first failed safely ("incident has not recovered yet") because CloudTrail had not yet indexed the rollback event; the retry succeeded. The captured episode is no longer listed as a live incident. |
| 04:30–04:56 | Partial controlled run (the live demo incident): configuration change 04:38:01, Duration ↑ 04:41, ConcurrentExecutions ↑ 04:43, latency alarm 04:45:48, OK 04:55:48. No errors (earlier stage than INC-0012). |
| 04:56 | Clicked **Analyze Incident** through the public CloudFront URL: HTTP 200 in 1.2 s. **96 % similar to INC-0012**: "Last time, Lambda Errors increased 3.2 minutes after the Lambda Duration alarm." INC-0009 69 %, INC-0007 37 % (below threshold, not shown). Asynchronous Bedrock step (Nova 2 Lite) completed in about 13 s, with 0 unsupported items dropped. |
| 04:58 | Captured screenshots of the public site (`screenshots/`). Updated the docs with the real numbers. |
| 06:20 | **Demo redesign after review:** a 96 % match against an identical incident captured 41 minutes earlier looked staged ("the same alarm fired twice"). The product's value is recognizing a *similar pattern* with a different cause. Replaced INC-0012 with a SEEDED_DEMO incident from ten weeks earlier with a different direct cause (RDS parameter change). The unchanged algorithm now scores **80 %**. Added "Why 80% similar?" (matches and differences) to the UI, and difference details to the factor reasons (for example, "configuration change, but to a different resource"). The captured run is archived as `captured-demo-run-2026-09-25.json` and its alarm episode is hidden from the live list. The Bedrock explanation now names the differences correctly. |
| 2026-09-25 15:48–15:52 | Agent Toolkit for AWS connected (AWS MCP Server + AWS skills). Verified the MCP server tools and made read-only calls through `aws___run_script`. Confirmed that CloudTrail recorded `aws-mcp.amazonaws.com` events. Evidence in `aws-mcp/` and [AWS_CONNECTION.md](AWS_CONNECTION.md). |
| 2026-09-25 16:20 | **Data consistency review of the public app.** Found four inconsistencies: live incidents started at the alarm but seeded ones at the change; INC-0009 exceeded the errors threshold without an errors alarm; evidence IDs were not in time order; a live incident showed OPEN with an end time. Fixed all four: Started is now always the alarm time; INC-0009 has its errors alarm and one resolution action; evidence IDs are renumbered in time order; new status RECOVERED ("Recovered · no resolution recorded"). Added `tests/test_consistency.py` (10 rules, 27 tests in total). |
| 2026-09-25 16:30 | **Demo redesign (different cause, similar pattern).** Live scenario: a Lambda configuration change (shorter downstream timeout plus retries) causes errors, then latency, then concurrency, then the latency alarm. INC-0012 (SEEDED_DEMO) is now a database connection pool change with the same degradation sequence. The unchanged algorithm scores it at about 80 %. The errors alarm threshold was raised to 10/min, so live errors stay below it. The UI now shows "Closest historical match" with the shared pattern, "What is different", and "What happened last time?". Seeded evidence is labeled fictional. The plan was reviewed and approved before apply (6 in-place updates). |
| 2026-09-25 16:44–17:09 | First re-run: the sequence was correct (errors 16:54, latency 16:56, concurrency 16:59, latency alarm 17:02), but the errors alarm fired at 17:06. Cause: the demo function's escalation step (heavy errors after 12 min, meant only for the full scenario) also ran for async invocations that were processed late after the partial run's load stopped. Fix: escalation only when the full scenario sets `ESCALATE=true`. The plan was approved and applied (3 updates). The failed episode `INC-20260925-1702` is hidden. |
| 2026-09-25 17:33–18:00 | Second re-run (live demo incident `INC-20260925-1750`): configuration change 17:41:02 (CloudTrail), Errors ↑ 17:43 (about 5 per minute, the errors alarm **did not** fire), Duration ↑ 17:46, ConcurrentExecutions ↑ 17:47, latency alarm 17:50:48, OK 18:00:48. A duplicate async delivery of the previous run's cleanup made one harmless configuration change at 17:29:25; it stays on the timeline as real evidence and is correctly not treated as the preceding change. |
| 2026-09-25 18:05 | Review of the analysis found two bugs: an earlier episode's alarm recovery showed on the timeline, and the rule-based text claimed "no other change was recorded". Also, the AI guessed what the change modified and mixed numbers. Fixed: timeline alarm events start at the trigger; the wording counts earlier changes; the prompt forbids guessing change content, requires exact numbers, and names the preceding change. Added a regression test (28 tests). Applied after approval (1 update). |
| 2026-09-25 18:18 | Public URL analysis: **82 % similar to INC-0012** (different cause: database connection pool change; shared pattern configuration change → errors → latency → concurrency → alarm). INC-0009 70 %. The AI explanation cites the preceding change CT-002 and quotes numbers exactly; 0 unsupported items dropped. Screenshots updated. |

## CloudTrail trace

The resources were created by the IAM principal used by the agent session. They can be
listed with:

```
aws cloudtrail lookup-events --region us-east-1 \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=incident-memory-demo-orders-api \
  --max-results 20
```

## Key decisions made with the agent

- **Isolation first.** Separate state bucket, name prefix, tags and IAM roles, plus a plan
  gate (`scripts/check_plan.py`) that refuses changes to non-Incident-Memory resources.
- **Deterministic similarity.** The LLM is never allowed to produce the percentage.
- **Real AWS evidence for the demo.** A dedicated Lambda workload whose configuration change
  (CloudTrail) actually causes the metric changes (CloudWatch). There is no RDS or always-on compute.
- **Async AI step.** API Gateway's 30-second limit means Bedrock runs asynchronously. The UI shows
  deterministic results first.
