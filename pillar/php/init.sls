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
    pm_max_children: 6
    pm_start_servers: 2
    pm_min_spare_servers: 1
    pm_max_spare_servers: 3
    pm_max_requests: 500
    request_terminate_timeout: 60
  monitoring:
    queue_warn: 5
    queue_crit: 10
