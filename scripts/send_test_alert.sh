#!/usr/bin/env bash
# Fire (or resolve) a synthetic Alertmanager-format alert at a Grafana IRM integration.
#
# Usage:
#   ./scripts/send_test_alert.sh <integration-url> [firing|resolved] [label]
#
# Example:
#   ./scripts/send_test_alert.sh "$INTEGRATION_URL" firing app-a
#   ./scripts/send_test_alert.sh "$INTEGRATION_URL" resolved app-a
#
# The label ends up in the alert title, so it is what your routing_regex matches.
set -euo pipefail

URL="${1:?integration URL required (printed by bootstrap_oncall.py)}"
STATUS="${2:-firing}"
LABEL="${3:-app-a}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "$STATUS" == "resolved" ]]; then ENDS="$NOW"; else ENDS="0001-01-01T00:00:00Z"; fi

curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "receiver": "grafana-irm",
  "status": "${STATUS}",
  "groupKey": "oncall-test-${LABEL}",
  "commonLabels": { "alertname": "OnCallTest-${LABEL}", "severity": "critical", "project": "${LABEL}" },
  "commonAnnotations": { "summary": "Synthetic test alert for ${LABEL}. Safe to ignore." },
  "alerts": [{
    "status": "${STATUS}",
    "labels": { "alertname": "OnCallTest-${LABEL}", "severity": "critical", "project": "${LABEL}" },
    "annotations": { "summary": "Synthetic test alert for ${LABEL}. Safe to ignore." },
    "startsAt": "${NOW}",
    "endsAt": "${ENDS}",
    "fingerprint": "oncall-test-${LABEL}"
  }]
}
JSON
echo
echo "Sent ${STATUS} test alert for '${LABEL}'."
