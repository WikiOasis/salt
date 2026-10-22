# TSPortal (https://github.com/WikiOasis/TSPortal), the Trust & Safety queue,
# on apps-us-east-021. The code, its build and its migrations are deployed by
# slop (`slop deploy -p tsportal`); this state owns the machine around it.
# Configuration lives in pillar/tsportal; secrets in pillar/private. The vhost is salt/nginx/files/safety.conf.jinja and the
# schema is created by mariadb.tsportal_db on db-other-us-east-011.
#
# PHP itself is not installed here: apps* already runs the shared php-fpm pool
# from the `php` state, and TSPortal serves out of it alongside Phorge and
# WOPortal.

include:
  - php

{%- set p = salt['pillar.get']('tsportal', {}) %}
{%- set path = p.get('path', '/srv/tsportal') %}
{%- set version = salt['pillar.get']('php:version', '8.4') %}
{%- set php = '/usr/bin/php' ~ version %}

{{ path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: True

tsportal-secrets:
  test.check_pillar:
    - present:
      - tsportal:app_key
      - tsportal:db_password
      - tsportal:s2s_secret
      - tsportal:authentik_client_id
      - tsportal:authentik_client_secret

{{ path }}/.env:
  file.managed:
    - source: salt://tsportal/files/tsportal.env.jinja
    - template: jinja
    - user: www-data
    - group: www-data
    - mode: '0640'
    - show_changes: False
    - require:
      - file: {{ path }}
      - test: tsportal-secrets

tsportal-writable:
  file.directory:
    - names:
      - {{ path }}/storage
      - {{ path }}/bootstrap/cache
    - user: www-data
    - group: www-data
    - mode: '0775'
    - makedirs: True
    - require:
      - file: {{ path }}

tsportal-worker-unit:
  file.managed:
    - name: /etc/systemd/system/tsportal-worker.service
    - source: salt://tsportal/files/tsportal-worker.service.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'

tsportal-worker:
  service.running:
    - name: tsportal-worker
    - enable: True
    - watch:
      - file: tsportal-worker-unit
      - file: {{ path }}/.env
    - require:
      - file: tsportal-writable

tsportal-scheduler-cron:
  cron.present:
    - name: cd {{ path }} && {{ php }} artisan schedule:run >> /dev/null 2>&1
    - user: www-data
    - minute: '*'
    - identifier: tsportal-scheduler
    - require:
      - file: {{ path }}/.env
