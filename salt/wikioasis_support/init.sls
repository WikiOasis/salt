# The support forum triage bot (https://github.com/WikiOasis/WikiOasisSupport)
# on apps-us-east-021. Non-secret configuration lives in
# pillar/wikioasis_support; the bot token, OpenAI key and DB password are in
# pillar/private. The schema is created by mariadb.wikioasis_support_db on
# db-other-us-east-011.
#
# There is no vhost: the bot holds an outbound websocket to Discord and listens
# on nothing. It sits on apps* rather than monitoring* only because that is
# where the database it talks to is already reachable and where the rest of the
# app deployments live.
#
# Node: the bot depends on openai@7, which requires Node >= 22, and Debian 13
# ships 20.19. Rather than pull NodeSource in — which replaces the distro
# `nodejs` package and would silently move TSPortal's and the deploy portal's
# Vite builds onto a different major on this same host — a private runtime is
# unpacked under /opt/nodejs and used by this service alone. Nothing else on
# the box sees it.

{%- set p = salt['pillar.get']('wikioasis_support', {}) %}
{%- set path = p.get('path', '/srv/wikioasis-support') %}
{%- set user = p.get('user', 'wikioasis-support') %}
{%- set node_version = p.get('node_version', '24.20.0') %}
{%- set node_root = '/opt/nodejs/node-v' ~ node_version ~ '-linux-x64' %}
{%- set node = node_root ~ '/bin/node' %}
{%- set npm = node_root ~ '/bin/npm' %}

wikioasis-support-packages:
  pkg.installed:
    - pkgs:
      - git
      - xz-utils

wikioasis_support_user:
  user.present:
    - name: {{ user }}
    - system: True
    - shell: /usr/sbin/nologin
    - home: {{ path }}
    - createhome: False

/opt/nodejs:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - makedirs: True

# source_hash points at the release's own SHASUMS256.txt, so the checksum is
# never transcribed into this file and bumping node_version in pillar is a
# one-line change rather than a version plus a hash to get right.
wikioasis-support-node:
  archive.extracted:
    - name: /opt/nodejs
    - source: https://nodejs.org/dist/v{{ node_version }}/node-v{{ node_version }}-linux-x64.tar.xz
    - source_hash: https://nodejs.org/dist/v{{ node_version }}/SHASUMS256.txt
    - user: root
    - group: root
    - if_missing: {{ node_root }}
    - enforce_toplevel: False
    - require:
      - pkg: wikioasis-support-packages
      - file: /opt/nodejs

{{ path }}:
  file.directory:
    - user: {{ user }}
    - group: {{ user }}
    - mode: '0755'
    - makedirs: True
    - require:
      - user: wikioasis_support_user

# git.latest runs as the service user, and /srv is root-owned, so the target
# has to exist and belong to it before the clone runs — same trap as tsportal.
wikioasis-support-clone:
  git.latest:
    - name: {{ p.get('repo', 'https://github.com/WikiOasis/WikiOasisSupport.git') }}
    - target: {{ path }}
    - rev: {{ p.get('rev', 'main') }}
    - user: {{ user }}
    - force_reset: True
    - require:
      - pkg: wikioasis-support-packages
      - file: {{ path }}

# An unset secret is not a rendering error — pillar.get falls back to '' and the
# env file is written with an empty value, so the highstate goes green and the
# bot crash-loops on a login failure that names neither the pillar nor the key.
# Fail here instead, where the message says which one is missing.
wikioasis-support-secrets:
  test.check_pillar:
    - present:
      - wikioasis_support:discord_token
      - wikioasis_support:openai_api_key
      - wikioasis_support:db_password

/etc/wikioasis-support.env:
  file.managed:
    - source: salt://wikioasis_support/files/wikioasis-support.env.jinja
    - template: jinja
    - user: root
    - group: {{ user }}
    - mode: '0640'
    # Holds the bot token and the OpenAI key. Anyone with the first can post as
    # the bot anywhere it has access.
    - show_changes: False
    - require:
      - user: wikioasis_support_user
      - test: wikioasis-support-secrets

/etc/wikioasis-support:
  file.directory:
    - user: root
    - group: {{ user }}
    - mode: '0750'

# The whole taxonomy — teams, categories, priorities and the prompt fragments
# that describe each of them — rendered straight out of pillar. This is the
# file to change to retune what the bot thinks "urgent" means; no code change
# and no release are involved.
/etc/wikioasis-support/triage.json:
  file.managed:
    - source: salt://wikioasis_support/files/triage.json.jinja
    - template: jinja
    - user: root
    - group: {{ user }}
    - mode: '0640'
    - require:
      - file: /etc/wikioasis-support

# Two states per build step, not one. The `onchanges` half is the update path;
# the `creates` half is what makes a re-run after a failed highstate actually
# retry — with only `onchanges`, an npm install that died halfway would never
# run again, because the checkout is already at the new commit and reports no
# change.
#
# devDependencies are installed and kept: the build needs typescript, and
# pruning afterwards would make the next `npm run build` fail on a box where
# only the update path runs.
wikioasis-support-npm-bootstrap:
  cmd.run:
    - name: {{ npm }} ci --no-audit --no-fund
    - cwd: {{ path }}
    - runas: {{ user }}
    - creates: {{ path }}/node_modules/.package-lock.json
    - env:
      # The service user's home IS the checkout, but npm still wants both of
      # these pointed somewhere it can write, and both survive git.latest —
      # which resets tracked files but does not clean untracked ones.
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
      - PATH: {{ node_root }}/bin:/usr/local/bin:/usr/bin:/bin
    - require:
      - git: wikioasis-support-clone
      - archive: wikioasis-support-node

wikioasis-support-npm-update:
  cmd.run:
    - name: {{ npm }} ci --no-audit --no-fund
    - cwd: {{ path }}
    - runas: {{ user }}
    - env:
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
      - PATH: {{ node_root }}/bin:/usr/local/bin:/usr/bin:/bin
    - onchanges:
      - git: wikioasis-support-clone
    - require:
      - cmd: wikioasis-support-npm-bootstrap

wikioasis-support-build-bootstrap:
  cmd.run:
    - name: {{ npm }} run build
    - cwd: {{ path }}
    - runas: {{ user }}
    - creates: {{ path }}/dist/index.js
    - env:
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
      - PATH: {{ node_root }}/bin:/usr/local/bin:/usr/bin:/bin
    - require:
      - cmd: wikioasis-support-npm-update

wikioasis-support-build-update:
  cmd.run:
    - name: {{ npm }} run build
    - cwd: {{ path }}
    - runas: {{ user }}
    - env:
      - HOME: {{ path }}
      - npm_config_cache: {{ path }}/.npm
      - PATH: {{ node_root }}/bin:/usr/local/bin:/usr/bin:/bin
    - onchanges:
      - git: wikioasis-support-clone
    - require:
      - cmd: wikioasis-support-build-bootstrap

# Validate the rendered taxonomy before the service is allowed to restart onto
# it. A duplicate category key or a team a category routes to but that does not
# exist fails the highstate here, with a message naming the field — instead of
# crash-looping the bot after the restart, when the only symptom is a forum
# that has quietly stopped being triaged.
wikioasis-support-config-check:
  cmd.run:
    - name: {{ node }} dist/index.js --check-config
    - cwd: {{ path }}
    - runas: {{ user }}
    - env:
      - TRIAGE_CONFIG_PATH: /etc/wikioasis-support/triage.json
      # --check-config returns before any of these is used, but loadEnv() still
      # asserts they are set, so give it throwaway values rather than the real
      # secrets — this runs in a command line that ends up in the job cache.
      - DISCORD_TOKEN: check
      - OPENAI_API_KEY: check
      - DB_HOST: check
      - DB_USER: check
      - DB_PASSWORD: check
      - DB_NAME: check
    - require:
      - cmd: wikioasis-support-build-update
      - file: /etc/wikioasis-support/triage.json
    - onchanges:
      - git: wikioasis-support-clone
      - file: /etc/wikioasis-support/triage.json

/etc/systemd/system/wikioasis-support.service:
  file.managed:
    - source: salt://wikioasis_support/files/wikioasis-support.service.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'

wikioasis-support:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/wikioasis-support.service
      - file: /etc/wikioasis-support.env
      - file: /etc/wikioasis-support/triage.json
      - git: wikioasis-support-clone
    - require:
      - cmd: wikioasis-support-build-update
      - cmd: wikioasis-support-config-check
      - file: /etc/wikioasis-support.env
      - file: /etc/wikioasis-support/triage.json
