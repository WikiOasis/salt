base:
   '*':
      - base
      - users
      - users.groups
      - private
   'db*':
      - mariadb
      - private
   'db-other-us-east-011*':
      - mariadb.db-other-us-east-011
   'metal* or *-us-east-0[0-9][0-9]*':
      - match: compound
      - metal
   'metal-us-east-01*':
      - metal.metal-us-east-01
   'metal-us-east-02*':
      - metal.metal-us-east-02
   'mw* or staging*':
      - match: compound
      - users.servers.mediawiki
      - php
   'proxy*':
      - haproxy
   'monitoring*':
      - monitoring
      - private
   'redis*':
      - redis
   'redis-us-east-011*':
      - redis.redis-us-east-011
   'redis-us-east-012*':
      - redis.redis-us-east-012
