{%- set s = salt['pillar.get']('slop', {}) %}
{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set webhooks = mw.get('webhooks', {}) %}
{%- set user = s.get('user', 'mwdeploy') %}
{%- set home = '/home/' ~ user %}
{%- set path = s.get('path', '/opt/slop') %}
{%- set key = home ~ '/.ssh/slop-conf' %}

include:
  - slop
  - mediawiki

{%- if not s.get('config_deploy_key') %}
slop-config-key-missing:
  test.fail_without_changes:
    - name: slop:config_deploy_key is empty; create pillar/private/slop.sls from pillar/private/slop.sls.example (a GitHub deploy key with write access to slop-conf)
{%- endif %}

slop-master-packages:
  pkg.installed:
    - pkgs:
      - composer
      - unzip
      - nodejs
      - npm
      - openssh-client

{{ key }}:
  file.managed:
    - contents_pillar: slop:config_deploy_key
    - user: {{ user }}
    - group: {{ user }}
    - mode: '0600'
    - show_changes: False
    - require:
      - file: /home/{{ user }}/.ssh

slop-github-known-host:
  ssh_known_hosts.present:
    - name: github.com
    - user: {{ user }}
    - enc: ssh-ed25519
    - key: AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
    - require:
      - file: /home/{{ user }}/.ssh

{{ path }}/config:
  file.directory:
    - user: {{ user }}
    - group: {{ user }}
    - mode: '0755'
    - require:
      - git: slop-code

slop-config-clone:
  cmd.run:
    - name: git clone --quiet --branch {{ s.get('config_branch', 'main') }} {{ s.get('config_repo', 'git@github.com:WikiOasis/slop-conf.git') }} {{ path }}/config
    - runas: {{ user }}
    - env:
      - GIT_SSH_COMMAND: ssh -i {{ key }} -o IdentitiesOnly=yes
    - unless: test -f {{ path }}/config/slop.yaml
    - require:
      - file: {{ path }}/config
      - file: {{ key }}
      - ssh_known_hosts: slop-github-known-host

slop-config-safe-directory:
  cmd.run:
    - name: git config --global --add safe.directory {{ path }}/config
    - unless: git config --global --get-all safe.directory | grep -qxF {{ path }}/config
    - require:
      - cmd: slop-config-clone

slop-config-ssh:
  cmd.run:
    - name: git -C {{ path }}/config config core.sshCommand "ssh -i {{ key }} -o IdentitiesOnly=yes"
    - runas: {{ user }}
    - unless: test "$(git -C {{ path }}/config config core.sshCommand)" = "ssh -i {{ key }} -o IdentitiesOnly=yes"
    - require:
      - cmd: slop-config-clone

slop-master-dirs:
  file.directory:
    - names:
      - {{ s.get('log_dir', '/var/log/slop') }}
      - {{ s.get('lock_dir', '/var/lib/slop/locks') }}
      {%- for dir in s.get('build_dirs', ['/srv/mediawiki-build']) %}
      - {{ dir }}
      {%- endfor %}
    - user: {{ user }}
    - group: {{ user }}
    - mode: '0755'
    - makedirs: True

/etc/slop:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/etc/slop/secrets.yaml:
  file.managed:
    - contents: |
        discord-webhook: {{ webhooks.get('discord', '') | tojson }}
        slack-webhook: {{ webhooks.get('slack', '') | tojson }}
    - user: root
    - group: {{ user }}
    - mode: '0640'
    - show_changes: False
    - require:
      - file: /etc/slop
