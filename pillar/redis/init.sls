redis:
  bind: 0.0.0.0
  port: 6379
  timeout: 0
  tcp_keepalive: 300
  loglevel: notice
  logfile: ""
  databases: 16
  maxmemory: 0
  maxmemory_policy: noeviction
  protected_mode: "yes"
  appendonly: "no"
  appendfsync: everysec
  save:
    - "900 1"
    - "300 10"
    - "60 10000"
