# Schema + user for TSPortal (https://github.com/WikiOasis/TSPortal), hosted
# here rather than on the db-c1 MediaWiki cluster since it's a small, unrelated
# app schema — same reasoning as mwdeploy_portal_db next door. Applied to
# db-other-us-east-011 only (see salt/top.sls); the portal itself runs on
# apps-us-east-021 and connects over the network, so the user is granted from
# '%' rather than 'localhost'.
{%- set db = salt['pillar.get']('tsportal:db', {}) %}
{%- set db_name = db.get('name', 'tsportal') %}
{%- set db_user = db.get('user', 'tsportal') %}
{%- set db_password = salt['pillar.get']('tsportal:db_password', '') %}

tsportal_db:
  cmd.run:
    - name: >
        mysql -e
        "CREATE DATABASE IF NOT EXISTS {{ db_name }};"
    - unless: >
        mysql -e "SHOW DATABASES LIKE {{ db_name }};" | grep -q {{ db_name }}
    - require:
      - pkg: install_mariadb
      - service: mariadb

tsportal_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        ALTER USER '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        GRANT ALL PRIVILEGES ON {{ db_name }}.* TO '{{ db_user }}'@'%';
        FLUSH PRIVILEGES;"
    - require:
      - cmd: tsportal_db
