#!/bin/bash
# Icinga2 host notification — incident.io alert events.
# Env vars set by the NotificationCommand: NOTIFICATIONTYPE HOSTNAME HOSTSTATE HOSTOUTPUT LONGDATETIME
set -euo pipefail
source /etc/icinga2/scripts/webhook_config.sh

[ "$NOTIFICATIONTYPE" = "RECOVERY" ] && STATUS="resolved" || STATUS="firing"

jq -n \
  --arg title    "[$NOTIFICATIONTYPE] Host $HOSTNAME is $HOSTSTATE" \
  --arg desc     "$HOSTOUTPUT ($LONGDATETIME)" \
  --arg dedup    "host-$HOSTNAME" \
  --arg status   "$STATUS" \
  '{
    title:             $title,
    description:       $desc,
    deduplication_key: $dedup,
    status:            $status,
    metadata: { type: "host" }
  }' \
| curl -sSL --max-time 30 -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $INCIDENTIO_TOKEN" \
    -d @- "$INCIDENTIO_URL"