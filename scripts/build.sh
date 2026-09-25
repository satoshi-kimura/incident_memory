#!/usr/bin/env bash
# Build Lambda packages into .build/ (API with the Anthropic SDK for Bedrock; demo functions have no deps).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.build"
rm -rf "$OUT" && mkdir -p "$OUT/api"

python3 -m pip install --quiet --no-compile \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.13 --only-binary=:all: \
  --target "$OUT/api" -r "$ROOT/backend/requirements.txt"
# boto3/botocore are provided by the Lambda runtime
rm -rf "$OUT/api"/boto3* "$OUT/api"/botocore* "$OUT/api"/s3transfer* "$OUT/api"/bin
cp -R "$ROOT/backend/app" "$OUT/api/app"
rm -f "$OUT/api/app/fixture.py"
find "$OUT/api" -name "__pycache__" -type d -prune -exec rm -rf {} +
(cd "$OUT/api" && zip -qr -X "$OUT/api.zip" .)

(cd "$ROOT/demo" && zip -q -X "$OUT/demo_orders_api.zip" orders_api.py && zip -q -X "$OUT/demo_scenario.zip" scenario.py)
ls -la "$OUT"/*.zip
