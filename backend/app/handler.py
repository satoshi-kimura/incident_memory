"""Lambda entry point (API Gateway HTTP API, payload v2) and async AI worker.

Public routes (the only inputs are application-defined incident IDs):
  GET  /api/incidents
  GET  /api/incidents/{id}
  POST /api/incidents/{id}/analyze
  GET  /api/health
"""
import json
import re
import time
import traceback

from . import analysis, config
from .log import log, metric
from .memory import summary_row

INCIDENT_ID = re.compile(r"^INC-(\d{4}|\d{8}-\d{4})$")

# Fields never returned to the browser.
PRIVATE_ANALYSIS_FIELDS = ("fingerprint",)


def lambda_handler(event, context):
    if event.get("task") == "ai":  # async self-invocation, not reachable from API Gateway
        analysis.run_ai(event["incident_id"], event["fingerprint"])
        return {"ok": True}

    started = time.time()
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    try:
        status, body = route(method, path, context)
    except Exception as e:  # noqa: BLE001
        log("backend_error", level="ERROR", path=path, method=method, error=type(e).__name__,
            detail=str(e)[:500], trace=traceback.format_exc()[-2000:])
        metric("BackendErrors", 1)
        status, body = 500, {"error": "internal_error", "message": "The request could not be completed. Please try again."}
    log("request", method=method, path=path, status=status, duration_ms=int((time.time() - started) * 1000))
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _error(status, code, message):
    return status, {"error": code, "message": message}


def route(method, path, context):
    parts = [p for p in path.split("/") if p]
    if parts[:1] != ["api"]:
        return _error(404, "not_found", "Unknown route.")
    parts = parts[1:]

    if parts == ["health"] and method == "GET":
        return 200, {"ok": True}

    if parts == ["incidents"] and method == "GET":
        memories, warnings = analysis.list_incidents()
        rows = sorted((summary_row(m) for m in memories), key=lambda r: r["started_at"] or "", reverse=True)
        return 200, {"incidents": rows, "warnings": warnings}

    if len(parts) >= 2 and parts[0] == "incidents":
        incident_id = parts[1]
        if not INCIDENT_ID.match(incident_id):
            return _error(400, "invalid_incident_id", "Incident ID is not valid.")
        try:
            if len(parts) == 2 and method == "GET":
                return 200, public_view(analysis.get_incident(incident_id))
            if len(parts) == 3 and parts[2] == "analyze" and method == "POST":
                memory, start = analysis.analyze(incident_id)
                if start:
                    start_ai(memory, context)
                return 200, public_view(memory)
        except analysis.NotFound:
            return _error(404, "incident_not_found", "No incident with this ID exists in the demo environment.")
        except analysis.NotAnalyzable as e:
            return _error(409, "not_analyzable", str(e))
        return _error(405, "method_not_allowed", "Method not allowed.")

    return _error(404, "not_found", "Unknown route.")


def start_ai(memory, context):
    """Run the Bedrock step asynchronously (API Gateway caps requests at 30 seconds)."""
    payload = {"task": "ai", "incident_id": memory["id"], "fingerprint": memory["analysis"]["fingerprint"]}
    if not config.FUNCTION_NAME:  # local development: run inline
        analysis.run_ai(memory["id"], payload["fingerprint"])
        memory.update(analysis.get_incident(memory["id"]))
        return
    import boto3
    try:
        boto3.client("lambda", region_name=config.REGION).invoke(
            FunctionName=config.FUNCTION_NAME, InvocationType="Event", Payload=json.dumps(payload).encode())
    except Exception as e:  # noqa: BLE001
        log("async_invoke_failure", level="ERROR", error=str(e)[:300])
        memory["analysis"]["ai_status"] = "UNAVAILABLE"
        memory["analysis"]["ai_error"] = "AI explanation could not be started. Showing rule-based analysis."
        from .store import get_store
        get_store().put(memory)


def public_view(memory):
    m = dict(memory)
    if "analysis" in m:
        m["analysis"] = {k: v for k, v in m["analysis"].items() if k not in PRIVATE_ANALYSIS_FIELDS}
    return m
