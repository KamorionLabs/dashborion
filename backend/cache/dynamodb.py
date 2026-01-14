"""
DynamoDB-backed cache implementation.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Iterable, Optional

import boto3
from boto3.dynamodb.conditions import Key

from .base import CacheBackend


class DynamoDBCache(CacheBackend):
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.environ.get("CACHE_TABLE_NAME")
        if not self.table_name:
            raise ValueError("CACHE_TABLE_NAME environment variable is not set")
        self._table = boto3.resource("dynamodb").Table(self.table_name)

    def get(self, pk: str, sk: str) -> Optional[Any]:
        response = self._table.get_item(Key={"pk": pk, "sk": sk})
        item = response.get("Item")
        if not item:
            return None
        ttl = item.get("ttl")
        if ttl and ttl < int(time.time()):
            return None
        payload = item.get("payload")
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
        return payload

    def set(self, pk: str, sk: str, value: Any, ttl_seconds: int, tags: Optional[Iterable[str]] = None) -> None:
        ttl = int(time.time()) + int(ttl_seconds)
        item = {
            "pk": pk,
            "sk": sk,
            "payload": json.dumps(value, default=str),
            "ttl": ttl,
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        if tags:
            item["tags"] = list(tags)
        self._table.put_item(Item=item)

    def invalidate_prefix(self, pk: str, sk_prefix: str) -> int:
        response = self._table.query(
            KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)
        )
        items = response.get("Items", [])
        if not items:
            return 0
        with self._table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        return len(items)
