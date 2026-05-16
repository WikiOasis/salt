/etc/sysctl.d/99-vrack.conf:
  file.managed:
    - contents: |
        net.ipv4.ip_forward=1
        net.ipv6.conf.all.forwarding=1
        net.ipv6.conf.all.proxy_ndp=1
    - user: root
    - group: root
    - mode: '0644'

apply_vrack_sysctl:
  cmd.run:
    - name: sysctl -p /etc/sysctl.d/99-vrack.conf
    - onchanges:
      - file: /etc/sysctl.d/99-vrack.conf

/etc/network/if-up.d/ipv6-vm-routing:
  file.managed:
    - source: salt://metal/ipv6_routing/files/ipv6-vm-routing.jinja
    - template: jinja
    - mode: '0755'
    - user: root
    - group: root

apply_ipv6_vm_routing:
  cmd.run:
    - name: /etc/network/if-up.d/ipv6-vm-routing
    - stateful: True
    - require:
      - file: /etc/network/if-up.d/ipv6-vm-routing
      - file: /etc/sysctl.d/99-vrack.conf
