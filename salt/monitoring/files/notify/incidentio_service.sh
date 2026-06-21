#!/bin/bash
# Icinga2 service notification — incident.io alert events.
# Env vars set by the NotificationCommand: NOTIFICATIONTYPE HOSTNAME SERVICENAME SERVICESTATE SERVICEOUTPUT LONGDATETIME
set -euo pipefail
source /etc/icinga2/scripts/webhook_config.sh

[ "$NOTIFICATIONTYPE" = "RECOVERY" ] && STATUS="resolved" || STATUS="firing"

jq -n \
  --arg title    "[$NOTIFICATIONTYPE] Service $SERVICENAME on $HOSTNAME is $SERVICESTATE" \
  --arg desc     "$SERVICEOUTPUT ($LONGDATETIME)" \
  --arg dedup    "service-$HOSTNAME-$SERVICENAME" \
  --arg status   "$STATUS" \
  '{
    title:             $title,
    description:       $desc,
    deduplication_key: $dedup,
    status:            $status
  }' \
| curl -sSL --max-time 30 -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $INCIDENTIO_TOKEN" \
    -d @- "$INCIDENTIO_URL"
