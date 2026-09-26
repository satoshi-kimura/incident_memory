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
| CloudTrail history not captured (imported real-world data) | preceding change |
| No resources identified | resource type |

"No change was found" (a successful CloudTrail query with no results) is **not** an
omission. It is the value `none`.

## Matching rules

- References are incidents with a known outcome: `RESOLVED` (resolution recorded) or `RECOVERED` (alarms returned
  to OK, no resolution recorded). Only incidents that **started before** the current one are compared.
- Ties are broken in favour of the most recent earlier incident, which is "last time".
- Matches below **60 %** are not shown as meaningful matches. The UI says
  *"No sufficiently similar historical incident was found."* and names the closest
  incident below the threshold.
- At most the **top 3** matches are shown.

## "What happened next"

For the top match, the application finds the last event that both incidents share
in the historical sequence. It then lists the historical events that came after it,
with their offsets measured from that shared event, for example:

> Last time: in INC-0012, Lambda Errors increased **4 minutes** after the Lambda Duration alarm.

This is a **historical comparison, not a prediction**, and the UI says so.

## Worked example (demo incident INC-20260925-1750, real AWS data, now CAPTURED_DEMO)

**Current incident (collected live, kept as CAPTURED_DEMO):** a Lambda configuration change at 17:41 UTC (shorter downstream timeout plus retries;
CloudTrail shows the API call, not the values). Then errors ↑ (17:43, about 5 per minute, below the errors alarm
threshold of 10), Duration ↑ (17:46), ConcurrentExecutions ↑ (17:47), and the latency alarm at 17:50. An earlier,
unrelated configuration change at 17:29 is in the window but is not the preceding change: the preceding change is
the most recent one before the first signal.

**INC-0012 (SEEDED_DEMO, 2026-07-14):** a **different direct cause**. A database connection pool change
(`/orders-api/db/pool-max` 20 → 100) was followed by DatabaseConnections ↑, then Errors ↑, FreeableMemory ↓, Duration ↑,
ConcurrentExecutions ↑, the latency alarm, the errors alarm (3 minutes later), the revert, and recovery.

| Factor | Points | Reason |
|---|---|---|
| Trigger | 25 / 25 | Same alarm: Lambda Duration (latency) |
| Event sequence | 20 / 20 | Same ordering of 5 of 5 events |
| Preceding change | 10 / 10 | Both configuration changes, **to different targets** (Lambda function vs database connection pool) |
| Signals | 20 / 25 | All 3 current signals seen; the historical incident also had DatabaseConnections ↑ and FreeableMemory ↓ |
| Resource type | 6.7 / 20 | Shared: Lambda function; only in the historical incident: RDS database, SSM parameter |
| **Score** | **82 %** | |

INC-0009 (DynamoDB capacity reduction → throttling → latency → alarm) scores 70 % as a different family of cause.
Everything else is below 60 % and not shown. The UI renders the breakdown as **"Why 82% similar?"**, followed by
**"What is different"** and **"What happened last time?"**.

## Worked example: exact recurrence (captured real-world data)

Cycle 27 of a production database free-memory alarm (2026-09-25 18:33 UTC) compared with cycle 26 (17:06 UTC):
trigger 25/25, resource type 20/20, signals 25/25 (RDS FreeableMemory ↓), sequence 20/20 (FreeableMemory ↓ → alarm);
the preceding-change factor is excluded because change history was not captured. Score: **100 %** of the
available factors. The differences are listed separately and do not change the score: lowest free memory
78.4 MiB vs 127.0 MiB, recovery after 863 min vs 2 min.
