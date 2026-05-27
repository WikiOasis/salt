# proxy* servers — deploy user in haproxy group for socket access
{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set deploy_user = mw.get('deploy_user', 'mwdeploy') %}

{{ deploy_user }}:
  user.present:
    - system: true
    - shell: /bin/bash
    - home: /home/{{ deploy_user }}
    - createhome: true
    - groups:
      - haproxy
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

# socat is needed to talk to the HAProxy socket
socat:
  pkg.installed: []
