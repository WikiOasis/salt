{%- set password = salt['pillar.get']('monitoring:mysqld_exporter_password') %}

prometheus_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS 'prom_exporter'@'127.0.0.1' IDENTIFIED BY '{{ password }}';
        ALTER USER 'prom_exporter'@'127.0.0.1' IDENTIFIED BY '{{ password }}';
        GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'prom_exporter'@'127.0.0.1';
        GRANT SELECT ON performance_schema.* TO 'prom_exporter'@'127.0.0.1';
        FLUSH PRIVILEGES;"
    - require:
      - pkg: install_mariadb
      - service: mariadb