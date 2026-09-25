"""Structured JSON logging + CloudWatch Embedded Metric Format for the app itself."""
import json
import sys
import time


def log(event, level="INFO", **fields):
    record = {"level": level, "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)


def metric(name, value, unit="Count", **dims):
    """Emit one EMF metric (namespace IncidentMemory/App). No API call needed."""
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "IncidentMemory/App",
                "Dimensions": [list(dims.keys())] if dims else [[]],
                "Metrics": [{"Name": name, "Unit": unit}],
            }],
        },
        name: value,
        **dims,
    }
    print(json.dumps(record), file=sys.stdout, flush=True)
