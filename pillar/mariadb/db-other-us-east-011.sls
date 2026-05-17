mariadb:
  datadir: /var/lib/mysql
  bind_address: 0.0.0.0
  key_buffer_size: 128M
  max_allowed_packet: 1G
  thread_stack: 192K
  thread_cache_size: 8
  max_connections: 100
  table_cache: 64
  expire_logs_days: 10
  innodb:
    buffer_pool_size: 1G
    log_file_size: 256M
    flush_log_at_trx_commit: 1
    file_per_table: true
