base:
   '*':
      - base
      - users
      - users.groups
   'db*':
      - mariadb
   'db-other-us-east-011*':
      - mariadb.db-other-us-east-011
   'metal* or *-us-east-0[0-9][0-9]*':
      - match: compound
      - metal
   'metal-us-east-01*':
      - metal.metal-us-east-01
   'metal-us-east-02*':
      - metal.metal-us-east-02
   'proxy*':
      - haproxy
   'monitoring*':
      - monitoring
      - private
