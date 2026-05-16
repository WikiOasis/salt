ip_forwarding_pkgs:
  pkg.installed:
    - pkgs:
      - iptables-persistent
      - dnsutils

ip_forwarding_script:
  file.managed:
    - name: /usr/local/sbin/apply-forwarding.sh
    - source: salt://metal/ip_forwarding/files/apply-forwarding.sh.jinja
    - template: jinja
    - mode: '0750'
    - user: root
    - group: root
    - require:
      - pkg: iptables-persistent
      - pkg: dnsutils

apply_ip_forwarding:
  cmd.run:
    - name: /usr/local/sbin/apply-forwarding.sh
    - onchanges:
      - file: ip_forwarding_script
    - require:
      - file: ip_forwarding_script
