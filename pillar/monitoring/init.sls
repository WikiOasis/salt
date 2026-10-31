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

  incidentio:
    host_alerts: true
    services:
      - opensearch
      - nginx_errors
      - mediawiki
      - haproxy_backends
      - ssh
      - salt_master
      - disk_root
      - redis
      - mariadb
      - procs
      - raid
      - smart

  slo:
    window: 28d
    objectives:
      mediawiki:
        title: MediaWiki requests
        objective: 99.5
        page: true
        errors: >-
          (sum(rate(haproxy_backend_http_responses_total{job="haproxy",backend="mediawiki",code="5xx"}[$window])) or vector(0))
          + (sum(rate(mediawiki_api_errors{error_code=~"internal_api_error_.*"}[$window])) or vector(0))
        total: >-
          sum(rate(haproxy_backend_http_responses_total{job="haproxy",backend="mediawiki"}[$window]))
      accounts:
        title: Accounts (accounts.wikioasis.org)
        objective: 99.5
        page: true
        haproxy_backend: accounts
        min_events: 30
      edits:
        title: Edit attempts
        objective: 99.5
        page: true
        min_events: 20
        errors: >-
          (sum(rate(mediawiki_edit_outcome_total{outcome="error"}[$window])) or vector(0))
          + (sum(rate(mediawiki_edit_failure_total{cause!="conflict"}[$window])) or vector(0))
        total: >-
          (sum(rate(mediawiki_edit_outcome_total[$window])) or vector(0))
          + (sum(rate(mediawiki_edit_failure_total{cause!="conflict"}[$window])) or vector(0))
      grafana:
        title: Grafana requests
        objective: 99.5
        page: true
        haproxy_backend: grafana
        min_events: 30
      authentik:
        title: Authentik requests (id.wikioasis.org)
        objective: 99.9
        page: true
        haproxy_backend: authentik
        min_events: 30
      tsportal:
        title: TSPortal requests (safety.wikioasis.org)
        objective: 99.9
        page: true
        haproxy_backend: tsportal
        min_events: 30
      phorge:
        title: Phorge requests
        objective: 99.5
        page: true
        haproxy_backend: phorge
        min_events: 30
      staging:
        title: Staging requests (test.wikioasis.org)
        objective: 95.0
        page: false
        haproxy_backend: staging
        min_events: 30
      opensearch:
        title: OpenSearch cluster availability
        objective: 99.99
        page: true
        good: >-
          (min(up{job="opensearch"})
          * (max(elasticsearch_cluster_health_status{job="opensearch",color=~"green|yellow"}) or vector(0)))
          or vector(0)
      databases:
        title: MariaDB availability
        objective: 99.99
        page: true
        good: >-
          avg(
            (mysql_up{job="mysqld"} and on(instance) up{job="mysqld"} == 1)
            or on(instance) (up{job="mysqld"} * 0)
          ) or vector(0)
      redis:
        title: Redis availability
        objective: 99.99
        page: true
        good: >-
          avg(
            (redis_up{job="redis"} and on(instance) up{job="redis"} == 1)
            or on(instance) (up{job="redis"} * 0)
          ) or vector(0)
      jobrunner:
        title: Job success
        objective: 99.5
        page: true
        min_events: 50
        errors: >-
          (sum(rate(jobrunner_jobs_total{status="failed"}[$window])) or vector(0))
          + (sum(rate(jobrunner_runner_status_total{status=~"error|kill|none"}[$window])) or vector(0))
        total: >-
          (sum(rate(jobrunner_jobs_total[$window])) or vector(0))
          + (sum(rate(jobrunner_runner_status_total{status=~"error|kill|none"}[$window])) or vector(0))
      job_latency:
        title: Jobs completed within 10m
        objective: 99.5
        page: true
        min_events: 50
        errors: >-
          (sum(rate(mediawiki_jobqueue_completion_seconds_bucket{le="+Inf"}[$window])) or vector(0))
          - (sum(rate(mediawiki_jobqueue_completion_seconds_bucket{le="600"}[$window])) or vector(0))
        total: >-
          sum(rate(mediawiki_jobqueue_completion_seconds_bucket{le="+Inf"}[$window]))

  jobqueue:
    stall_for: 15m
    growth_threshold: 10000
    growth_window: 15m
    imbalance_ratio: 1.1
    imbalance_window: 1h
    imbalance_min_backlog: 1000
    backlog_threshold: 50000
    backlog_for: 30m
    abandoned_growth_threshold: 100
