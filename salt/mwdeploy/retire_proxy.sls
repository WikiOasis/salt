{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set deploy_user = mw.get('deploy_user', 'mwdeploy') %}

{%- if mw.get('deploy_ssh_public_key') %}
mwdeploy-proxy-key-retired:
  ssh_auth.absent:
    - user: {{ deploy_user }}
    - names:
      - {{ mw['deploy_ssh_public_key'] }}
{%- endif %}
