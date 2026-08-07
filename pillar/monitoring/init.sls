monitoring:
  icinga_api_user: root
  ido_db_name: icingadb
  ido_db_user: icingadb
  web_db_name: icingaweb
  director_db_name: icingaweb
  director_db_user: icingadb

  grafana:
    admin_user: admin

  prometheus:
    retention: 30d

  # Which alerts are paged out to incident.io. Discord and Slack still get
  # notified for every monitored service regardless of what is listed here —
  # this list only controls what wakes someone up.
  #
  # Names must match the Icinga service object names in
  # salt/monitoring/files/icinga2/salt-hosts.conf.jinja. A name that no host
  # runs is silently ignored, so it is safe to list a service before it exists.
  incidentio:
    # Send a page whenever any host goes down (hostalive check).
    host_alerts: true
    services:
      - opensearch
      - nginx_errors
      - mediawiki
      - haproxy_backends
      - ssh
      - salt_minion
      - salt_master
      - disk_root
      - redis
      - mariadb
      - procs
      - raid
      - smart
