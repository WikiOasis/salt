# Metal-host NRPE checks (SMART + RAID) — apply to metal* via top.sls.
# Requires: nagios-nrpe-server, smartmontools already installed on target.

smartmontools:
  pkg.installed

/etc/sudoers.d/nagios-smartctl:
  file.managed:
    - contents: "nagios ALL=(root) NOPASSWD: /usr/sbin/smartctl\n"
    - mode: '0440'
    - user: root
    - group: root

/usr/lib/nagios/plugins/check_smart.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_smart.sh
    - mode: '0755'
    - user: root
    - group: root

/usr/lib/nagios/plugins/check_raid.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_raid.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/smart.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/smart.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_smart.sh
      - file: /etc/sudoers.d/nagios-smartctl
    - watch_in:
      - service: nagios-nrpe-server

/etc/nagios/nrpe.d/raid.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/raid.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_raid.sh
    - watch_in:
      - service: nagios-nrpe-server
