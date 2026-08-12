# Non-secret configuration for incidentio-sync (mirrors the incident.io status
# page into Discord — https://github.com/WikiOasis/incidentio-sync).
# The webhook URL is a secret and lives in pillar/private/init.sls — see
# pillar/private/init.sls.example for the shape.

incidentio_sync:
  feed_url: https://status.wikioasis.org/feed.atom
  state_file: /var/lib/incidentio-sync/state.json
  status_page_url: status.wikioasis.org
  poll_interval: 15
  prune_after_days: 30
  log_level: INFO
