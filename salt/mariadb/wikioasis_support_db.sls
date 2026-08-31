# Schema + user for the support triage bot
# (https://github.com/WikiOasis/WikiOasisSupport), hosted here rather than on
# the db-c1 MediaWiki cluster since it's a small, unrelated app schema — same
# reasoning as tsportal_db and mwdeploy_portal_db next door. Applied to
# db-other-us-east-011 only (see salt/top.sls); the bot itself runs on
# apps-us-east-021 and connects over the network, so the user is granted from
# '%' rather than 'localhost'.
#
# The tables are created by the bot on boot, not here — it applies its own
# schema idempotently at startup, so this state only has to hand it a database
# it can write to.
{%- set db = salt['pillar.get']('wikioasis_support:db', {}) %}
{%- set db_name = db.get('name', 'wikioasis_support') %}
{%- set db_user = db.get('user', 'wikioasis_support') %}
{%- set db_password = salt['pillar.get']('wikioasis_support:db_password', '') %}

wikioasis_support_db:
  cmd.run:
    - name: >
        mysql -e
        "CREATE DATABASE IF NOT EXISTS {{ db_name }};"
    - unless: >
        mysql -e "SHOW DATABASES LIKE {{ db_name }};" | grep -q {{ db_name }}
    - require:
      - pkg: install_mariadb
      - service: mariadb

wikioasis_support_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        ALTER USER '{{ db_user }}'@'%' IDENTIFIED BY '{{ db_password }}';
        GRANT ALL PRIVILEGES ON {{ db_name }}.* TO '{{ db_user }}'@'%';
        FLUSH PRIVILEGES;"
    - require:
      - cmd: wikioasis_support_db
