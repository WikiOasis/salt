# The deploy portal itself (https://github.com/WikiOasis/mw-deploy), on the
# Salt master. See mw-deploy's docs/SALT-INTEGRATION.md sections 3-4 and
# docs/OPERATIONS.md. nginx/php-fpm vhost lives in mwdeploy.portal.nginx;
# publisher_acl for www-data lives in mwdeploy.portal.master_acl.

{%- set p = salt['pillar.get']('mwdeploy_portal', {}) %}
{%- set path = p.get('path', '/srv/deploy-portal') %}
{%- set php_version = p.get('php_version', '8.4') %}

mwdeploy-portal-packages:
  pkg.installed:
    - pkgs:
      - php{{ php_version }}-fpm
      - php{{ php_version }}-cli
      - php{{ php_version }}-mysql
      - php{{ php_version }}-mbstring
      - php{{ php_version }}-xml
      - php{{ php_version }}-curl
      - php{{ php_version }}-intl
      - php{{ php_version }}-zip
      - php{{ php_version }}-bcmath
      - nodejs
      - npm
      - git
      - composer

# The portal's schema lives on db-other-us-east-011 (mariadb.portal_db, applied
# via salt/top.sls), not a local mariadb on the salt master — see
# pillar/mwdeploy_portal db.host and portal.env.jinja's DB_HOST.

mwdeploy-portal-clone:
  git.latest:
    - name: {{ p.get('repo', 'https://github.com/WikiOasis/mw-deploy.git') }}
    - target: {{ path }}
    - rev: {{ p.get('rev', 'main') }}
    - user: www-data
    - force_reset: True
    - require:
      - pkg: mwdeploy-portal-packages

{{ path }}/.env:
  file.managed:
    - source: salt://mwdeploy/portal/files/portal.env.jinja
    - template: jinja
    - user: www-data
    - group: www-data
    - mode: '0640'
    - show_changes: False
    - require:
      - git: mwdeploy-portal-clone

mwdeploy-portal-composer:
  cmd.run:
    - name: composer install --no-dev --optimize-autoloader --no-interaction
    - cwd: {{ path }}
    - runas: www-data
    - env:
      - COMPOSER_HOME: {{ path }}/.composer
    - onchanges:
      - git: mwdeploy-portal-clone

mwdeploy-portal-writable:
  file.directory:
    - names:
      - {{ path }}/storage
      - {{ path }}/bootstrap/cache
    - user: www-data
    - group: www-data
    - mode: '0775'
    - recurse:
      - user
      - group
      - mode
    - require:
      - cmd: mwdeploy-portal-composer

# public/build is gitignored and bakes in VITE_REVERB_* at build time, so this
# must run after .env exists — changing Reverb's public host/port without a
# rebuild leaves the browser dialling the old websocket URL.
mwdeploy-portal-assets:
  cmd.run:
    - name: npm ci && npm run build
    - cwd: {{ path }}
    - runas: www-data
    - onchanges:
      - git: mwdeploy-portal-clone
      - file: {{ path }}/.env
    - require:
      - file: {{ path }}/.env
      - cmd: mwdeploy-portal-composer

mwdeploy-portal-migrate:
  cmd.run:
    - name: php artisan migrate --force
    - cwd: {{ path }}
    - runas: www-data
    - onchanges:
      - git: mwdeploy-portal-clone
    - require:
      - file: {{ path }}/.env
      - cmd: mwdeploy-portal-composer

# Roles + the 13 permissions only. updateOrCreate under the hood, so this is
# idempotent on every highstate and is how new permissions arrive on upgrade —
# it creates no user accounts.
mwdeploy-portal-seed:
  cmd.run:
    - name: php artisan db:seed --force
    - cwd: {{ path }}
    - runas: www-data
    - require:
      - cmd: mwdeploy-portal-migrate

mwdeploy-portal-optimise:
  cmd.run:
    - name: php artisan optimize
    - cwd: {{ path }}
    - runas: www-data
    - onchanges:
      - git: mwdeploy-portal-clone
      - file: {{ path }}/.env
    - require:
      - cmd: mwdeploy-portal-migrate

mwdeploy-worker-unit:
  file.managed:
    - name: /etc/systemd/system/mwdeploy-worker.service
    - source: salt://mwdeploy/portal/files/mwdeploy-worker.service
    - user: root
    - group: root
    - mode: '0644'

# Restarting mid-deployment orphans the running deployment (stays "running"
# forever — nothing else marks it failed), so this is intentionally not swept
# into any generic "restart services on highstate" convention.
mwdeploy-worker:
  service.running:
    - name: mwdeploy-worker
    - enable: True
    - watch:
      - file: mwdeploy-worker-unit
      - file: {{ path }}/.env
      - git: mwdeploy-portal-clone
    - require:
      - cmd: mwdeploy-portal-migrate

mwdeploy-reverb-unit:
  file.managed:
    - name: /etc/systemd/system/mwdeploy-reverb.service
    - source: salt://mwdeploy/portal/files/mwdeploy-reverb.service
    - user: root
    - group: root
    - mode: '0644'

mwdeploy-reverb:
  service.running:
    - name: mwdeploy-reverb
    - enable: True
    - watch:
      - file: mwdeploy-reverb-unit
      - file: {{ path }}/.env
    - require:
      - cmd: mwdeploy-portal-migrate
