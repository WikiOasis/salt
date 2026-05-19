icinga_monitor_user:
  mysql_user.present:
    - name: icinga_monitor
    - host: '%'
    - password: {{ salt['pillar.get']('monitoring:monitoring_db_password') }}
    - require:
      - service: mariadb

icinga_monitor_grant:
  mysql_grants.present:
    - grant: usage
    - database: '*.*'
    - user: icinga_monitor
    - host: '%'
    - require:
      - mysql_user: icinga_monitor_user
