{%- set dns_hosts = salt['pillar.get']('dns_hosts', {}) %}

/usr/local/sbin/assign-host:
  file.managed:
    - source: salt://metal/dns_dhcp/files/assign-host
    - user: root
    - group: root
    - mode: "0750"

{%- for hostname, h in dns_hosts.items() %}
assign_host_{{ hostname }}:
  cmd.run:
    - name: assign-host add {{ hostname }} {{ h.mac if h.mac else '~' }} {{ h.ip }}
    - unless: assign-host list | awk 'NR>2{print $1}' | grep -qxF '{{ hostname }}'
    - require:
      - file: /usr/local/sbin/assign-host
{%- endfor %}
