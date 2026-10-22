{%- set sal = salt['pillar.get']('sal', {}) %}
{%- set members = [] %}
{%- for group in salt['pillar.get']('server_groups', ['ops']) %}
  {%- do members.extend(salt['pillar.get']('groups', {}).get(group, {}).get('members', [])) %}
{%- endfor %}
{%- do members.extend(salt['pillar.get']('sal:local_users', [])) %}
{%- set members = members | unique | list %}

include:
  - users

{%- if not sal.get('host_token') %}
sal-client-token-missing:
  test.fail_without_changes:
    - name: sal:host_token is empty; create pillar/private/sal.sls from pillar/private/sal.sls.example on the master
{%- endif %}

sal-client-deps:
  pkg.installed:
    - name: python3

sal-group:
  group.present:
    - name: sal
    - system: True
    - members: {{ members | tojson }}
    - require:
      - sls: users

/etc/sal:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/etc/sal/client.json:
  file.managed:
    - source: salt://sal/files/client.json.jinja
    - template: jinja
    - user: root
    - group: sal
    - mode: '0640'
    - show_changes: False
    - require:
      - file: /etc/sal
      - group: sal-group

/usr/local/bin/log:
  file.managed:
    - source: salt://sal/files/sal_client.py
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - pkg: sal-client-deps

/usr/local/bin/log-cli:
  file.managed:
    - source: salt://sal/files/sal_client.py
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - pkg: sal-client-deps
