/etc/icinga2/conf.d/salt-hosts.conf:
  file.managed:
    - source: salt://monitoring/files/icinga2/salt-hosts.conf.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - watch_in:
      - service: icinga2
