{%- set raw_private %}{% include 'private/sal.sls' ignore missing %}{% endset %}
{%- set private = ((raw_private | load_yaml) or {}).get('sal', {}) %}

sal:
  secret: {{ private.get('secret', '') | yaml_dquote }}
  db_password: {{ private.get('db_password', '') | yaml_dquote }}
  server:
    listen_host: 10.0.2.124
    listen_port: 8740
    poll_interval: 5
    max_attempts: 50
    max_message: 2000
  wiki:
    enabled: True
    api: https://meta.wikioasis.org/w/api.php
    page: Tech:Server admin log
    page_url: https://meta.wikioasis.org/wiki/Tech:Server_admin_log
    user: {{ private.get('wiki_user', '') | yaml_dquote }}
    password: {{ private.get('wiki_password', '') | yaml_dquote }}
  phorge:
    enabled: True
    base: https://phorge.wikioasis.org
    hook: https://phorge.wikioasis.org/sal/hook
    token: {{ private.get('phorge_token', '') | yaml_dquote }}
