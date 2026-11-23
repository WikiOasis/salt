redis:
  port: 6379
  timeout: 0
  tcp_keepalive: 5000
  loglevel: notice
  logfile: ""
  databases: 16
  maxmemory: 0
  maxmemory_policy: noeviction
  protected_mode: "no"
  appendonly: "no"
  appendfsync: everysec
