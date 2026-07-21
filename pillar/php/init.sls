php:
  version: "8.4"
  extensions:
    - fpm
    - mysql
    - xml
    - mbstring
    - intl
    - curl
    - gd
    - zip
    - apcu
    - igbinary
    - redis
  extra_packages:
    - php-excimer
    - php-luasandbox
  fpm:
    pool: www
    listen: ""
    pm: dynamic
    pm_max_children: 10
    pm_start_servers: 6
    pm_min_spare_servers: 6
    pm_max_spare_servers: 8
    pm_max_requests: 500
    request_terminate_timeout: 60
    memory_limit: 300M
  monitoring:
    queue_warn: 5
    queue_crit: 10
  opcache:
    enable: true
    enable_cli: false
    memory_consumption: 1024
    interned_strings_buffer: 512
    max_accelerated_files: 100000
    max_wasted_percentage: 10
    validate_timestamps: true
    revalidate_freq: 10
    save_comments: false
    jit: tracing
    jit_buffer_size: 128M
