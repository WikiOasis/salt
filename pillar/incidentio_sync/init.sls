# Non-secret configuration for incidentio-sync (mirrors the incident.io status
# page into Discord — https://github.com/WikiOasis/incidentio-sync).
# The webhook URL is a secret and lives in pillar/private/init.sls — see
# pillar/private/init.sls.example for the shape.

incidentio_sync:
  # Origin of the status page. The sync polls the page itself (not the Atom
  # feed) so it can see healthy components and full update timelines, and
  # falls back to <origin>/api/v1/summary if the page can't be parsed.
  status_page_url: https://status.wikioasis.org
  state_file: /var/lib/incidentio-sync/state.json
  poll_interval: 15
  # Sticky message at the bottom of the channel listing every component and its
  # current status. Set to False to post incident messages only.
  overview_enabled: True
  prune_after_days: 30
  log_level: INFO
