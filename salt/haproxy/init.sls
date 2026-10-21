{%- set haproxy = salt['pillar.get']('haproxy', {}) %}
{%- set has_routes = haproxy.get('routes') | length > 0 %}

haproxy:
  pkg.installed:
    - refresh: True

socat:
  pkg.installed: []

/etc/haproxy/haproxy.cfg:
  file.managed:
    - source: salt://haproxy/files/haproxy.cfg.jinja
    - template: jinja
    - user: root
    - group: haproxy
    - mode: '0640'
    - require:
      - pkg: haproxy

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
{%- if has_routes %}
      - file: /etc/haproxy/routes.map
{%- endif %}
    - require:
      - pkg: haproxy
      - pkg: socat