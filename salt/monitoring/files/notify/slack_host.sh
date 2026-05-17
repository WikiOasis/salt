#!/bin/bash
# Icinga2 host notification — Slack webhook.
# Env vars set by the NotificationCommand: NOTIFICATIONTYPE HOSTNAME HOSTSTATE HOSTOUTPUT LONGDATETIME
set -euo pipefail
source /etc/icinga2/scripts/webhook_config.sh

jq -n \
  --arg type    "$NOTIFICATIONTYPE" \
  --arg host    "$HOSTNAME" \
  --arg state   "$HOSTSTATE" \
  --arg output  "$HOSTOUTPUT" \
  --arg dt      "$LONGDATETIME" \
  '{
    username:   "Icinga2",
    icon_emoji: ":rotating_light:",
    text: "*[\($type)]* Host *\($host)* is *\($state)*\n\($output)\n\($dt)"
  }' \
| curl -fsSL -X POST -H "Content-Type: application/json" -d @- "$SLACK_WEBHOOK_URL"
