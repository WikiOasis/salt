#!/bin/bash
# Icinga2 service notification — Discord webhook.
# Env vars set by the NotificationCommand: NOTIFICATIONTYPE HOSTNAME SERVICENAME SERVICESTATE SERVICEOUTPUT LONGDATETIME
set -euo pipefail
source /etc/icinga2/scripts/webhook_config.sh

jq -n \
  --arg type    "$NOTIFICATIONTYPE" \
  --arg host    "$HOSTNAME" \
  --arg svc     "$SERVICENAME" \
  --arg state   "$SERVICESTATE" \
  --arg output  "$SERVICEOUTPUT" \
  --arg dt      "$LONGDATETIME" \
  '{
    username: "Icinga2",
    content: "**[\($type)]** Service **\($svc)** on **\($host)** is **\($state)**\n\($output)\n\($dt)"
  }' \
| curl -fsSL -X POST -H "Content-Type: application/json" -d @- "$DISCORD_WEBHOOK_URL"
