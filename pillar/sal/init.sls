{%- set raw_private %}{% include 'private/sal.sls' ignore missing %}{% endset %}
{%- set private = ((raw_private | load_yaml) or {}).get('sal', {}) %}
{%- set secret = private.get('secret', '') %}

sal:
  server_url: http://salt-us-east-021.ovvin.wonet:8740
  host_token: {{ (secret ~ ':' ~ grains['id']) | sha256 if secret else "''" }}
  db:
    host: db-other-us-east-011.ovvin.wonet
    name: sal
    user: sal
