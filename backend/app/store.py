"""Incident Memory storage: DynamoDB in AWS, in-process dict for local runs/tests.

Each memory is stored as a JSON document string plus a few top-level attributes
used for listing. Cached Bedrock results (keyed by evidence fingerprint) and the daily Bedrock call
counter live in the same table.
"""
import json
from datetime import datetime, timezone

from . import config


class MemoryStore:
    def __init__(self):
        self.items = {}
        self.usage = {}
        self.ai = {}

    def put_ai(self, fingerprint, result):
        self.ai[fingerprint] = json.loads(json.dumps(result))

    def get_ai(self, fingerprint):
        return self.ai.get(fingerprint)

    def put(self, memory):
        self.items[memory["id"]] = json.loads(json.dumps(memory))

    def get(self, incident_id):
        m = self.items.get(incident_id)
        return json.loads(json.dumps(m)) if m else None

    def list(self):
        return [json.loads(json.dumps(m)) for m in self.items.values()]

    def take_bedrock_call(self, limit):
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.usage.get(day, 0) >= limit:
            return False
        self.usage[day] = self.usage.get(day, 0) + 1
        return True


class DynamoStore:
    def __init__(self):
        import boto3
        self.table = boto3.resource("dynamodb", region_name=config.REGION).Table(config.TABLE_NAME)

    def put(self, memory):
        self.table.put_item(Item={
            "id": memory["id"],
            "kind": "incident",
            "status": memory.get("status"),
            "started_at": memory.get("started_at"),
            "doc": json.dumps(memory, separators=(",", ":")),
        })

    def put_ai(self, fingerprint, result):
        self.table.put_item(Item={"id": f"ai#{fingerprint}", "kind": "ai",
                                  "doc": json.dumps(result, separators=(",", ":"))})

    def get_ai(self, fingerprint):
        item = self.table.get_item(Key={"id": f"ai#{fingerprint}"}).get("Item")
        return json.loads(item["doc"]) if item else None

    def get(self, incident_id):
        item = self.table.get_item(Key={"id": incident_id}).get("Item")
        return json.loads(item["doc"]) if item and item.get("kind") == "incident" else None

    def list(self):
        items, kwargs = [], {"FilterExpression": "#k = :k", "ExpressionAttributeNames": {"#k": "kind"},
                             "ExpressionAttributeValues": {":k": "incident"}}
        while True:
            resp = self.table.scan(**kwargs)
            items.extend(resp["Items"])
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return [json.loads(i["doc"]) for i in items]

    def take_bedrock_call(self, limit):
        """Atomically reserve one Bedrock call for today; False when the daily cap is reached."""
        from botocore.exceptions import ClientError
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            self.table.update_item(
                Key={"id": f"usage#{day}"},
                UpdateExpression="SET #k = :u ADD #c :one",
                ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
                ExpressionAttributeNames={"#c": "count", "#k": "kind"},
                ExpressionAttributeValues={":one": 1, ":limit": limit, ":u": "usage"},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise


_store = None


def get_store():
    global _store
    if _store is None:
        _store = MemoryStore() if config.STORE_BACKEND == "memory" else DynamoStore()
    return _store
