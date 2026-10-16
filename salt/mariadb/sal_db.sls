{%- set db = salt['pillar.get']('sal:db', {}) %}
{%- set db_name = db.get('name', 'sal') %}
{%- set db_user = db.get('user', 'sal') %}
{%- set db_host = salt['pillar.get']('sal:db_client_host', '%') %}
{%- set db_password = salt['pillar.get']('sal:db_password', '') %}

sal_db:
  cmd.run:
    - name: >
        mysql -e
        "CREATE DATABASE IF NOT EXISTS {{ db_name }} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    - unless: >
        mysql -e "SHOW DATABASES LIKE '{{ db_name }}';" | grep -q {{ db_name }}
    - require:
      - pkg: install_mariadb
      - service: mariadb

sal_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS '{{ db_user }}'@'{{ db_host }}' IDENTIFIED BY '{{ db_password }}';
        ALTER USER '{{ db_user }}'@'{{ db_host }}' IDENTIFIED BY '{{ db_password }}';
        GRANT ALL PRIVILEGES ON {{ db_name }}.* TO '{{ db_user }}'@'{{ db_host }}';
        FLUSH PRIVILEGES;"
    - unless: test -z '{{ db_password }}'
    - require:
      - cmd: sal_db
