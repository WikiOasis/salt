# MariaDB backup NRPE checks — apply to db* via top.sls.
# Requires: nagios-nrpe-server already installed on target.

/usr/lib/nagios/plugins/check_mariadb_backup.sh:
  file.managed:
    - source: salt://mariadb/files/nrpe/check_mariadb_backup.sh
    - user: root
    - group: root
    - mode: '0755'

/etc/nagios/nrpe.d/mariadb_backup.cfg:
  file.managed:
    - source: salt://mariadb/files/nrpe/mariadb_backup.cfg
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_mariadb_backup.sh
    - watch_in:
      - service: nagios-nrpe-server
