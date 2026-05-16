{%- set dns_hosts = salt['pillar.get']('dns_hosts', {}) %}

/usr/local/sbin/assign-host:
  file.managed:
    - source: salt://dns-dhcp/files/assign-host
    - user: root
    - group: root
    - mode: "0750"

{%- for hostname, h in dns_hosts.items() %}
assign_host_{{ hostname }}:
  cmd.run:
    - name: assign-host add {{ hostname }} {{ h.mac if h.mac else '~' }} {{ h.ip }}
{%- if h.mac %}
    - unless: grep -q ',{{ hostname }},' /etc/dnsmasq.d/static-hosts.conf
{%- else %}
    - unless: grep -q '^{{ hostname }}[[:space:]]' /etc/bind/zones/ovvin.wonet.zone
{%- endif %}
    - require:
      - file: /usr/local/sbin/assign-host
{%- endfor %}
