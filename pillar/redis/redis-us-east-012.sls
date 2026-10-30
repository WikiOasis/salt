redis:
  bind: 0.0.0.0
  maxmemory: 3gb
  maxmemory_policy: allkeys-lru
  save:
    - "900 1"
    - "300 10"
    - "60 10000"
  exporter:
    check_keys:
      - 'db0=*:jobqueue:*:l-unclaimed'
      - 'db0=*:jobqueue:*:z-abandoned'
