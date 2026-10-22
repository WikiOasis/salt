include:
  - slop.user

{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set prod_path = mw.get('prod_path', '/srv/mediawiki') %}

{{ prod_path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: true
