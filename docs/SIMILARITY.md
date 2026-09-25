# Similarity Algorithm

Incident Memory calculates similarity **deterministically in application code**
(`backend/app/similarity.py`). Amazon Bedrock may explain a score in plain English,
but it never calculates, estimates or changes one. Its output is validated, and any
explanation that contains a percentage is discarded.

## Inputs: the pattern

Every Incident Memory stores a normalized `pattern` (`backend/app/memory.py → build_pattern`)
derived only from structured data:

| Feature | Example | Source |
|---|---|---|
| `trigger` | `{service: Lambda, metric: Duration, family: latency}` | CloudWatch alarm definition |
| `resource_types` | `["lambda:function"]` | signals + CloudTrail changes |
| `signals` | `["Lambda.Duration:up", "Lambda.ConcurrentExecutions:up"]` | CloudWatch metrics → signal detection |
| `sequence` | `change:configuration → Lambda.Duration:up → Lambda.ConcurrentExecutions:up → alarm:Lambda.Duration` | first occurrence of each token, in time order |
| `offsets_min` | `{"Lambda.Duration:up": 2.0, ...}` | minutes after the preceding change (or the first signal) |
| `preceding_change` | `configuration` | see below |

**Metric families** (failure types): `latency` (Duration, Latency, TargetResponseTime),
`errors` (Errors, 5XX), `throttling` (Throttles, ThrottledRequests), `saturation`
(ConcurrentExecutions, CPU, memory), `traffic` (Invocations, request counts).

**Preceding change**: the most recent CloudTrail change at or before the first signal:
`deployment` (UpdateFunctionCode, PublishVersion, …), `configuration`
(UpdateFunctionConfiguration, PutParameter, UpdateTable, …) or `scaling`
(PutFunctionConcurrency, …). Without one, a first signal of increased traffic
means `traffic`; otherwise the value is `none`.

## Factors and weights

| # | Factor | Weight | Value in [0, 1] |
|---|---|---|---|
| 1 | Trigger / alarm signature | 25 | 1.0 same service and metric · 0.7 same metric family · 0.3 same service only · 0 otherwise |
| 2 | AWS service / resource type | 20 | Jaccard(resource types) = \|C ∩ H\| / \|C ∪ H\| |
| 3 | Observed signal overlap | 25 | 0.5 · \|C ∩ H\| / \|C\| + 0.5 · Jaccard(C, H) |
| 4 | Event sequence | 20 | (concordant pairs / all pairs of shared events) × (shared events / current events), 0 if fewer than 2 shared |
| 5 | Preceding change | 10 | 1.0 same category (including both `none`) · 0.5 both AWS changes of different categories · 0 otherwise |

```
score = round(100 × Σ weightᵢ × valueᵢ / Σ weightᵢ)      (sums over available factors)
```

**Why a blend for signal overlap.** A new incident is often at an *earlier stage*
than a historical one: it has seen latency increase, while last time errors
followed. Coverage (`|C ∩ H| / |C|`) rewards a historical incident that contains
everything observed so far. Jaccard stops a historical incident with many unrelated
signals from matching everything.

**Why the sequence value is scaled by coverage.** Two shared events in the same
order would otherwise count as a perfect ordering match. Scaling by the share of
current events that also appear in the historical sequence prevents that.

## Unavailable factors

When evidence is genuinely unavailable, the factor is **omitted** and the score is
normalized over the remaining weights. The UI lists omitted factors with the reason.

| Condition | Omitted factor(s) |
|---|---|
| No alarm trigger recorded | trigger |
| CloudWatch metric query failed | signals, sequence |
| No significant metric change detected | signals |
| CloudTrail query failed | preceding change |
| No resources identified | resource type |

"No change was found" (a successful CloudTrail query with no results) is **not** an
omission. It is the value `none`.

## Matching rules

- Only incidents with status `RESOLVED` are used as references (they have a known outcome).
- Matches below **60 %** are not shown as meaningful matches. The UI says
  *"No sufficiently similar historical incident was found."* and names the closest
  incident below the threshold.
- At most the **top 3** matches are shown.
- Ties are broken by incident ID so that results are stable.

## "What happened next"

For the top match, the application finds the last event that both incidents share
in the historical sequence. It then lists the historical events that came after it,
with their offsets measured from that shared event, for example:

> Last time: in INC-0012, Lambda Errors increased **4 minutes** after the Lambda Duration alarm.

This is a **historical comparison, not a prediction**, and the UI says so.

## Worked example (live demo incident INC-20260925-0445, real AWS data)

**Current incident (LIVE_DEMO):** a Lambda configuration change at 04:38 UTC, then Duration ↑ (04:41),
then ConcurrentExecutions ↑ (04:43), then the latency alarm (04:45).

**INC-0012 (SEEDED_DEMO, 2026-07-14):** a **different direct cause**. An RDS parameter group change
(max_connections 400 → 1000) was followed by DatabaseConnections ↑, then Lambda Duration ↑, then
ConcurrentExecutions ↑, then the latency alarm, then Errors ↑ (4 minutes later), then the errors alarm, then the revert.

| Factor | Points | Reason |
|---|---|---|
| Trigger | 25 / 25 | Same alarm: Lambda Duration (latency) |
| Event sequence | 20 / 20 | Same ordering of 4 of 4 events |
| Preceding change | 10 / 10 | Both configuration changes, **to different resources** (Lambda function vs RDS parameter group) |
| Signals | 18.8 / 25 | Both current signals seen; the historical incident also had DatabaseConnections ↑ and Errors ↑ |
| Resource type | 6.7 / 20 | Shared: Lambda function; only in the historical incident: RDS database, RDS parameter group |
| **Score** | **80 %** | |

INC-0009 (a DynamoDB capacity change) scores 69 %. INC-0007 (a traffic spike with no change
event) scores 37 % and is not shown. The UI renders this breakdown as **"Why 80% similar?"**,
with ✓ for full matches and ◐ for partial ones.
