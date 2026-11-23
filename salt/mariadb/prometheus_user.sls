{%- set password = salt['pillar.get']('monitoring:mysqld_exporter_password') %}

# mysqld_exporter connects over the unix socket (MariaDB listens on the vRack
# address only, not 127.0.0.1), so the user is @localhost.
prometheus_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS 'prom_exporter'@'localhost' IDENTIFIED BY '{{ password }}';
        ALTER USER 'prom_exporter'@'localhost' IDENTIFIED BY '{{ password }}';
        GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'prom_exporter'@'localhost';
        GRANT SELECT ON performance_schema.* TO 'prom_exporter'@'localhost';
        DROP USER IF EXISTS 'prom_exporter'@'127.0.0.1';
        FLUSH PRIVILEGES;"
    - require:
      - pkg: install_mariadb
      - service: mariadb
