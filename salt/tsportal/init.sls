# TSPortal (https://github.com/WikiOasis/TSPortal), the Trust & Safety queue,
# on apps-us-east-021. Configuration lives in pillar/tsportal; secrets in
# pillar/private. The vhost is salt/nginx/files/safety.conf.jinja and the
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

# Debian 13 ships Node 20.19, which is the floor for the Vite 8 this builds
# with. `composer` is the distro package; the app is installed with --no-dev.
tsportal-build-packages:
  pkg.installed:
    - pkgs:
      - git
      - nodejs
      - npm
      - composer

tsportal-clone:
  git.latest:
    - name: {{ p.get('repo', 'https://github.com/WikiOasis/TSPortal.git') }}
    - target: {{ path }}
    - rev: {{ p.get('rev', 'main') }}
    - user: www-data
    - force_reset: True
    - require:
      - pkg: tsportal-build-packages

{{ path }}/.env:
  file.managed:
    - source: salt://tsportal/files/tsportal.env.jinja
    - template: jinja
    - user: www-data
    - group: www-data
    - mode: '0640'
    # Holds MW_S2S_SECRET, the OAuth secret and the R2 keys — anyone with the
    # first can file reports and read any account's standing.
    - show_changes: False
    - require:
      - git: tsportal-clone

# Two states, not one, for each build step. The `onchanges` half is the update
# path; the `creates` half is what makes a re-run after a failed highstate
# actually retry — with only `onchanges`, a composer install that died halfway
# would never run again, because by then the checkout is already at the new
# commit and reports no change.
tsportal-composer-bootstrap:
  cmd.run:
    - name: composer install --no-dev --optimize-autoloader --no-interaction
    - cwd: {{ path }}
    - runas: www-data
    - creates: {{ path }}/vendor/autoload.php
    - env:
      # www-data's home (/var/www) is root-owned, so anything that wants a
      # cache dir has to be pointed somewhere it can actually write. Both of
      # these sit inside the checkout and survive git.latest, which resets
      # tracked files but does not clean untracked ones.
      - HOME: {{ path }}
      - COMPOSER_HOME: {{ path }}/.composer
    - require:
      - git: tsportal-clone

tsportal-composer-update:
  cmd.run:
    - name: composer install --no-dev --optimize-autoloader --no-interaction
    - cwd: {{ path }}
    - runas: www-data
    - env:
      # www-data's home (/var/www) is root-owned, so anything that wants a
      # cache dir has to be pointed somewhere it can actually write. Both of
      # these sit inside the checkout and survive git.latest, which resets
      # tracked files but does not clean untracked ones.
      - HOME: {{ path }}
      - COMPOSER_HOME: {{ path }}/.composer
    - onchanges:
      - git: tsportal-clone
    - require:
      - cmd: tsportal-composer-bootstrap

tsportal-writable:
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
      - cmd: tsportal-composer-update

# public/build is gitignored, so it has to be built here. It bakes in the
# VITE_* values, hence the dependency on .env rather than on the checkout alone.
tsportal-assets-bootstrap:
  cmd.run:
    - name: npm ci && npm run build
    - cwd: {{ path }}
    - runas: www-data
    - env:
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
    - creates: {{ path }}/public/build/manifest.json
    - require:
      - file: {{ path }}/.env
      - cmd: tsportal-composer-update

tsportal-assets-update:
  cmd.run:
    - name: npm ci && npm run build
    - cwd: {{ path }}
    - runas: www-data
    - env:
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
    - onchanges:
      - git: tsportal-clone
      - file: {{ path }}/.env
    - require:
      - cmd: tsportal-assets-bootstrap

# Unconditional: migrations are idempotent, and gating them on the checkout
# changing is what leaves a box a schema behind after a partly-failed run.
tsportal-migrate:
  cmd.run:
    - name: {{ php }} artisan migrate --force
    - cwd: {{ path }}
    - runas: www-data
    - require:
      - file: {{ path }}/.env
      - cmd: tsportal-composer-update

# No `db:seed` here, deliberately. Unlike the deploy portal's, TSPortal's
# DatabaseSeeder creates a "Test User" account rather than roles and
# permissions — running it on every highstate would keep planting a staff
# account in the Trust & Safety portal. Access is granted through
# MW_BOOTSTRAP_ADMINS once, then from inside the portal.

tsportal-optimise:
  cmd.run:
    - name: {{ php }} artisan optimize
    - cwd: {{ path }}
    - runas: www-data
    - onchanges:
      - git: tsportal-clone
      - file: {{ path }}/.env
    - require:
      - cmd: tsportal-migrate

# The worker is where every background thing happens: pushing to the wiki,
# walking erasures through their stages, retiring expired actions, Slack.
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
      - git: tsportal-clone
    - require:
      - cmd: tsportal-migrate

# The scheduler only enqueues; the worker above does the work. Two things need
# a clock: ExpireDueSanctions (every ten minutes) and AdvanceDataRemovals
# (every minute). The first matters more than it looks — nothing edits a
# sanction when its time runs out, so without this the wiki goes on refusing a
# login for a ban that ended overnight, and the person it affects cannot log in
# to tell anyone. Everything else is dispatched at the moment it happens.
tsportal-scheduler-cron:
  cron.present:
    - name: cd {{ path }} && {{ php }} artisan schedule:run >> /dev/null 2>&1
    - user: www-data
    - minute: '*'
    - identifier: tsportal-scheduler
    - require:
      - cmd: tsportal-migrate
