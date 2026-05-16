{%- set vm = salt['pillar.get']('proxmox:vms:' ~ grains['id'], {}) %}
{%- set vmid = vm.get('vmid') %}
{%- set host_cfg = salt['pillar.get']('proxmox:hosts:' ~ vm.get('metal_host', ''), {}) %}
{%- set prefix = host_cfg.get('ipv6_prefix', '') %}
{%- set gw_ll = host_cfg.get('vm_gateway_ll', '') %}
{%- set iface = vm.get('interface', 'ens18') %}

{%- if vmid is not none %}

/etc/network/interfaces.d/ipv6.conf:
  file.managed:
    - source: salt://metal/vm_ipv6/files/interfaces.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'

ipv6_addr_{{ vmid }}:
  cmd.run:
    - name: ip -6 addr add {{ prefix }}::{{ vmid }}/128 dev {{ iface }}
    - unless: ip -6 addr show dev {{ iface }} | grep -q '{{ prefix }}::{{ vmid }}/128'

ipv6_default_route_{{ vmid }}:
  cmd.run:
    - name: ip -6 route add default via {{ gw_ll }} dev {{ iface }}
    - unless: ip -6 route show | grep -q 'default via {{ gw_ll }}'
    - require:
      - cmd: ipv6_addr_{{ vmid }}

{%- endif %}
