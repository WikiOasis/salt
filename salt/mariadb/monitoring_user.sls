{% set password = salt['pillar.get']('monitoring:monitoring_db_password') %}

icinga_monitor_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS 'icinga_monitor'@'%' IDENTIFIED BY '{{ password }}';
        ALTER USER 'icinga_monitor'@'%' IDENTIFIED BY '{{ password }}';"
    - require:
      - pkg: install_mariadb
      - service: mariadb

icinga_monitor_grant:
  cmd.run:
    - name: >
        mysql -e
        "GRANT USAGE ON *.* TO 'icinga_monitor'@'%';"
    - require:
      - cmd: icinga_monitor_user