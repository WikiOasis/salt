{%- set haproxy = salt['pillar.get']('haproxy', {}) %}
{%- set has_routes = haproxy.get('routes') | length > 0 %}
{%- set ep = haproxy.get('error_pages', {}) %}
{%- set ep_path = ep.get('path', '/opt/errorpages') %}
{%- set ep_codes = ep.get('codes', [400, 403, 404, 405, 408, 410, 413, 425, 429, 500, 501, 502, 503, 504]) %}

haproxy:
  pkg.installed:
    - refresh: True

socat:
  pkg.installed: []

git:
  pkg.installed:
    - pkgs:
      - git
      - python3

haproxy-errorpages-code:
  git.latest:
    - name: {{ ep.get('repo', 'https://github.com/WikiOasis/ErrorPages.git') }}
    - target: {{ ep_path }}
    - rev: {{ ep.get('rev', 'main') }}
    - branch: {{ ep.get('rev', 'main') }}
    - user: root
    - force_reset: True
    - submodules: False
    - require:
      - pkg: git

haproxy-errorpages-build:
  cmd.run:
    - name: python3 -I {{ ep_path }}/build.py http /etc/haproxy/errors
    - unless: test -f /etc/haproxy/errors/{{ ep_codes[0] }}.http && test -z "$(find {{ ep_path }}/build.py {{ ep_path }}/src -newer /etc/haproxy/errors/{{ ep_codes[0] }}.http)"
    - shell: /bin/bash
    - require:
      - git: haproxy-errorpages-code
      - file: /etc/haproxy/errors/maintenance.html

/etc/haproxy/haproxy.cfg:
  file.managed:
    - source: salt://haproxy/files/haproxy.cfg.jinja
    - template: jinja
    - user: root
    - group: haproxy
    - mode: '0640'
    - require:
      - pkg: haproxy
      - cmd: haproxy-errorpages-build

/etc/haproxy/errors/maintenance.html:
  file.managed:
    - source: salt://haproxy/files/errors/maintenance.html
    - makedirs: True
    - user: root
    - group: haproxy
    - mode: '0644'
    - require:
      - pkg: haproxy

{%- if has_routes %}
/etc/haproxy/routes.map:
  file.managed:
    - source: salt://haproxy/files/routes.map.jinja
    - template: jinja
    - user: root
    - group: haproxy
    - mode: '0640'
    - require:
      - pkg: haproxy
{%- endif %}

haproxy_service:
  service.running:
    - name: haproxy
    - enable: True
    - reload: True
    - watch:
      - file: /etc/haproxy/haproxy.cfg
      - file: /etc/haproxy/errors/maintenance.html
      - cmd: haproxy-errorpages-build
{%- if has_routes %}
      - file: /etc/haproxy/routes.map
{%- endif %}
    - require:
      - pkg: haproxy
      - pkg: socat