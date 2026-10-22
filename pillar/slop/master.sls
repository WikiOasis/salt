{%- set raw_private %}{% include 'private/slop.sls' ignore missing %}{% endset %}
{%- set private = ((raw_private | load_yaml) or {}).get('slop', {}) %}

slop:
  config_deploy_key: {{ private.get('config_deploy_key', '') | yaml_dquote }}
  log_dir: /var/log/slop
  lock_dir: /var/lib/slop/locks

sal:
  local_users:
    - mwdeploy
