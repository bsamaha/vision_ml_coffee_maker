#!/bin/sh
# Run the alert Workflow on Roboflow's hosted API with one picture.
#
#   scripts/cloud-alert.sh you@example.com                          # empty tank: sends the refill email
#   scripts/cloud-alert.sh you@example.com workflow/samples/full.jpg  # full tank: sends nothing
#
# The API key is ROBOFLOW_API_KEY from the environment or from .env in the repository root.
# Every run spends Roboflow credits, and a run under 17.5 fl oz sends one email.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
email=${1:-${ALERT_EMAIL:-}}
image=${2:-$root/workflow/samples/empty.jpg}
workspace=${ROBOFLOW_WORKSPACE:-blake-samaha-s-workspace}
workflow=${ROBOFLOW_WORKFLOW:-custom-workflow}

if [ -z "$email" ]; then
  echo "usage: scripts/cloud-alert.sh <email> [image]" >&2
  exit 2
fi
if [ ! -f "$image" ]; then
  echo "no image at $image" >&2
  exit 2
fi
key=${ROBOFLOW_API_KEY:-}
if [ -z "$key" ] && [ -f "$root/.env" ]; then
  key=$(sed -n 's/^[[:space:]]*ROBOFLOW_API_KEY[[:space:]]*=[[:space:]]*//p' "$root/.env" | tr -d "\"'" | head -n 1)
fi
if [ -z "$key" ]; then
  echo "no ROBOFLOW_API_KEY in the environment or $root/.env" >&2
  exit 2
fi

body=$(mktemp)
response=$(mktemp)
trap 'rm -f "$body" "$response"' EXIT
printf '{"inputs": {"image": {"type": "base64", "value": "%s"}, "alert_email": "%s"}}' \
  "$(base64 < "$image" | tr -d '\n')" "$email" > "$body"

status=$(curl --silent --show-error --max-time 180 --output "$response" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' \
  --header "Authorization: Bearer $key" \
  --data @"$body" \
  "https://serverless.roboflow.com/$workspace/workflows/$workflow")

echo "HTTP $status, $(basename "$image") to $email"
uv run --no-project python - "$response" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except ValueError:
    print(open(sys.argv[1], encoding="utf-8", errors="replace").read()[:500])
    raise SystemExit(1)
outputs = data.get("outputs") if isinstance(data, dict) else None
if not outputs:
    print(json.dumps(data)[:500])
    raise SystemExit(1)
out = outputs[0]
gauge = out.get("gauge_oz")
print("gauge_oz:", None if gauge is None else round(gauge, 1))
print("person:", out.get("person"))
email = out.get("email") or {}
print("email:", email.get("message") or "not sent (the level is not under the refill line)")
PY
