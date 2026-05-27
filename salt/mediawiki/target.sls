# mw* application servers — deploy user, authorized key, rsync sudo, /srv/mediawiki dir
{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set deploy_user = mw.get('deploy_user', 'mwdeploy') %}
{%- set prod_path = mw.get('prod_path', '/srv/mediawiki') %}

{{ deploy_user }}:
  user.present:
    - system: true
    - shell: /bin/bash
    - home: /home/{{ deploy_user }}
    - createhome: true
  group.present: []

/home/{{ deploy_user }}/.ssh:
  file.directory:
    - user: {{ deploy_user }}
    - group: {{ deploy_user }}
    - mode: '0700'
    - require:
      - user: {{ deploy_user }}

{%- if mw.get('deploy_ssh_public_key') %}
{{ deploy_user }}_ssh_auth:
  ssh_auth.present:
    - user: {{ deploy_user }}
    - names:
      - {{ mw['deploy_ssh_public_key'] }}
    - require:
      - file: /home/{{ deploy_user }}/.ssh
{%- endif %}

# Allow rsync to write to /srv/mediawiki (owned by www-data)
/etc/sudoers.d/mwdeploy_target:
  file.managed:
    - contents:
      - "{{ deploy_user }} ALL=(root) NOPASSWD: /usr/bin/rsync"
    - user: root
    - group: root
    - mode: '0440'

{{ prod_path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: true
