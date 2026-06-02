base:
   '*':
      - base
      - users
      - private
   'apps*':
      - php
      - private
   'bastion*':
      - users.servers.bastion
   'db*':
      - mariadb
      - private
   'db-other-us-east-011*':
      - mariadb.db-other-us-east-011
   'db-pc-us-east-011*':
      - mariadb.db-pc-us-east-011
   'db-c1-us-east-021*':
      - mariadb.db-c1-us-east-021
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
      - nginx
      - mediawiki
   'proxy*':
      - haproxy
      - mediawiki
   'monitoring*':
      - monitoring
      - metal
      - private
   'task*':
      - users.servers.mediawiki
      - php
      - nginx
      - mediawiki
      - mediawiki.jobrunner

   'opensearch*':
      - opensearch
   'redis*':
      - redis
   'redis-us-east-011*':
      - redis.redis-us-east-011
   'redis-us-east-012*':
      - redis.redis-us-east-012
