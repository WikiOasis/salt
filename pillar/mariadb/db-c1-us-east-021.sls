mariadb:
  # Offset this host's backups to 12:00 UTC so they don't collide with the
  # other db servers (default 01:00 full / 02:00 incremental) on the shared
  # backup destination.
  backup:
    schedule:
      full_hour: '12'
      incremental_hour: '12'
  server_id: 1021
  datadir: /var/lib/mysql
  bind_address: 0.0.0.0
  key_buffer_size: 128M
  max_allowed_packet: 1G
  thread_stack: 192K
  thread_cache_size: 8
  max_connections: 1000
  table_cache: 64
  expire_logs_days: 10
  innodb:
    buffer_pool_size: 20G
    log_file_size: 2G
    flush_log_at_trx_commit: 1
    file_per_table: true
