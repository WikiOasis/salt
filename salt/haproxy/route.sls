{%- set haproxy = salt['pillar.get']('haproxy', {}) %}
{%- set socket = haproxy.get('stats_socket', '/run/haproxy/admin.sock') %}
{%- set routes = haproxy.get('routes', []) %}

# Manages the HAProxy hostname → backend routing map from pillar.
#
# Pillar shape (in haproxy:routes):
#   - hostname: app.example.com
#     backend: app_servers
#     active: true     # false removes the entry from the map
#
# Applying this state:
#   - Writes /etc/haproxy/routes.map from pillar (active entries only)
#   - On file change, syncs the live in-memory map via the runtime socket
#     without requiring a full haproxy reload
#
# Run with: salt 'proxy*' state.apply haproxy.route

/etc/haproxy/routes.map:
  file.managed:
    - source: salt://haproxy/files/routes.map.jinja
    - template: jinja
    - user: root
    - group: haproxy
    - mode: '0640'
    - require:
      - pkg: haproxy

# Sync the in-memory map with the file contents on change.
# Uses clear + re-add so stale entries are purged without a reload.
haproxy_sync_routes:
  cmd.run:
    - name: |
        echo "clear map /etc/haproxy/routes.map" | socat stdio {{ socket }}
        while IFS=' ' read -r hostname backend remainder; do
          [ -n "$hostname" ] || continue
          echo "add map /etc/haproxy/routes.map $hostname $backend" | socat stdio {{ socket }}
        done < /etc/haproxy/routes.map
    - onchanges:
      - file: /etc/haproxy/routes.map
    - require:
      - pkg: socat
      - file: /etc/haproxy/routes.map

# Per-route idempotent adds for active routes (runs on every apply to catch
# entries that may have been lost after a haproxy restart).
{%- for route in routes %}
{%- if route.get('active', true) %}
haproxy_route_add_{{ route.hostname | replace('.', '_') }}:
  cmd.run:
    - name: echo "add map /etc/haproxy/routes.map {{ route.hostname }} {{ route.backend }}" | socat stdio {{ socket }}
    - unless: echo "show map /etc/haproxy/routes.map" | socat stdio {{ socket }} | grep -q '^{{ route.hostname }} '
    - require:
      - pkg: socat
      - file: /etc/haproxy/routes.map

{%- else %}
haproxy_route_del_{{ route.hostname | replace('.', '_') }}:
  cmd.run:
    - name: echo "del map /etc/haproxy/routes.map {{ route.hostname }}" | socat stdio {{ socket }}
    - onlyif: echo "show map /etc/haproxy/routes.map" | socat stdio {{ socket }} | grep -q '^{{ route.hostname }} '
    - require:
      - pkg: socat
      - file: /etc/haproxy/routes.map

{%- endif %}
{%- endfor %}
