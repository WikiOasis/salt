# Schema + user for the mw-deploy portal (https://github.com/WikiOasis/mw-deploy),
# hosted here rather than on the db-c1 MediaWiki cluster since it's a small,
# unrelated app schema. Applied to db-other-us-east-011 only (see salt/top.sls);
# the portal itself lives on the salt master and connects over the network, so
# the user is granted from '%' rather than 'localhost' — same pattern as
# icinga_monitor in mariadb/monitoring_user.sls.
{%- set db = salt['pillar.get']('mwdeploy_portal:db', {}) %}
{%- set db_name = db.get('name', 'mwdeploy') %}
{%- set db_user = db.get('user', 'mwdeploy') %}
{%- set db_password = salt['pillar.get']('mwdeploy_portal:db_password', '') %}

mwdeploy_portal_db:
  cmd.run:
    - name: >
        mysql -e
        "CREATE DATABASE `{{ db_name }}`;"
    - unless: >
        mysql -e "SHOW DATABASES LIKE '{{ db_name }}';" | grep -q {{ db_name }}
    - require:
      - pkg: install_mariadb
      - service: mariadb

mwdeploy_portal_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        ALTER USER '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        GRANT ALL PRIVILEGES ON `{{ db_name }}`.* TO '{{ db_user }}'@'%';
        FLUSH PRIVILEGES;"
    - require:
      - cmd: mwdeploy_portal_db
