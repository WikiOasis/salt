squid:
  pkg.installed: []
  service.running:
    - enable: True
    - watch:
      - file: /etc/squid/squid.conf
    - require:
      - pkg: squid

/etc/squid/squid.conf:
  file.managed:
    - source: salt://metal/apt_proxy/files/squid.conf
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: squid

# The apt proxy config is only needed before Salt manages a host.
# Enforce it is absent once Salt takes over.
/etc/apt/apt.conf.d/99proxy:
  file.absent
