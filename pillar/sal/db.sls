{%- set raw_private %}{% include 'private/sal.sls' ignore missing %}{% endset %}
{%- set private = ((raw_private | load_yaml) or {}).get('sal', {}) %}

sal:
  db_password: {{ private.get('db_password', '') | yaml_dquote }}
  db_client_host: '%'
