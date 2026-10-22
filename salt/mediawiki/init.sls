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

{%- if mw.get('deploy_ssh_private_key') %}
/home/{{ deploy_user }}/.ssh/id_ed25519:
  file.managed:
    - contents_pillar: mediawiki:deploy_ssh_private_key
    - user: {{ deploy_user }}
    - group: {{ deploy_user }}
    - mode: '0600'
    - show_changes: False
    - require:
      - file: /home/{{ deploy_user }}/.ssh
{%- endif %}

{{ prod_path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: true
