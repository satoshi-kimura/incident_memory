"""Static configuration and the demo-resource allowlist.

Everything the analyzer may look at is declared here. Public requests only carry
application-defined incident IDs; they never supply ARNs, metric names, regions,
namespaces or CloudTrail queries.
"""
import os

REGION = "us-east-1"
TABLE_NAME = os.environ.get("TABLE_NAME", "incident-memory-incidents")
STORE_BACKEND = os.environ.get("STORE_BACKEND", "dynamodb")  # "dynamodb" | "memory"
FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")  # set by Lambda; used for async AI step

# Bedrock (model is configurable; see docs/ARCHITECTURE.md)
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-5")
BEDROCK_CLIENT = os.environ.get("BEDROCK_CLIENT", "mantle")  # "mantle" | "invoke" | "converse" | "disabled"
BEDROCK_DAILY_CALL_LIMIT = int(os.environ.get("BEDROCK_DAILY_CALL_LIMIT", "100"))
BEDROCK_TIMEOUT_SECONDS = float(os.environ.get("BEDROCK_TIMEOUT_SECONDS", "90"))
PROMPT_VERSION = "2026-09-26.1"

# Evidence collection results are reused for this long to protect AWS API quotas.
COLLECTION_CACHE_SECONDS = int(os.environ.get("COLLECTION_CACHE_SECONDS", "60"))
# A failed AI step for unchanged evidence is not retried within this window.
AI_RETRY_AFTER_SECONDS = int(os.environ.get("AI_RETRY_AFTER_SECONDS", "600"))

# ---------------------------------------------------------------- demo allowlist

DEMO_FUNCTION = "incident-memory-demo-orders-api"

# Alarms are queried by exact name only.
DEMO_ALARMS = [
    "incident-memory-demo-orders-api-latency-high",
    "incident-memory-demo-orders-api-errors-high",
    "incident-memory-demo-orders-api-throttles-high",
]

# CloudTrail lookups are restricted to these resource names; results are re-filtered.
CLOUDTRAIL_RESOURCES = [
    {"name": DEMO_FUNCTION, "service": "Lambda", "resource_type": "lambda:function"},
]

# Metrics collected for every analysis (AWS/Lambda metrics of the demo function).
# abs_min: minimum absolute change that counts as significant.
WATCHED_METRICS = [
    {"id": "duration", "namespace": "AWS/Lambda", "metric": "Duration", "stat": "Average", "unit": "Milliseconds", "abs_min": 150},
    {"id": "concurrency", "namespace": "AWS/Lambda", "metric": "ConcurrentExecutions", "stat": "Maximum", "unit": "Count", "abs_min": 1},
    {"id": "errors", "namespace": "AWS/Lambda", "metric": "Errors", "stat": "Sum", "unit": "Count", "abs_min": 3},
    {"id": "throttles", "namespace": "AWS/Lambda", "metric": "Throttles", "stat": "Sum", "unit": "Count", "abs_min": 3},
    {"id": "invocations", "namespace": "AWS/Lambda", "metric": "Invocations", "stat": "Sum", "unit": "Count", "abs_min": 30},
]
METRIC_DIMENSIONS = [{"Name": "FunctionName", "Value": DEMO_FUNCTION}]
METRIC_SERVICE = "Lambda"
METRIC_RESOURCE = DEMO_FUNCTION
METRIC_RESOURCE_TYPE = "lambda:function"
# Metrics whose missing datapoints mean zero (Sum of events).
ZERO_FILL_METRICS = {"Errors", "Throttles"}

# Analysis window around the incident trigger (minutes).
WINDOW_BEFORE_MIN = 30
WINDOW_AFTER_MIN = 15

# Relative change needed for a metric movement to count as a signal.
SIGNAL_REL_THRESHOLD = 0.25
