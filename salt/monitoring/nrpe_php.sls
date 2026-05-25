install_libfcgi:
  pkg.installed:
    - name: libfcgi-bin

nagios_in_adm_group_php:
  user.present:
    - name: nagios
    - groups:
      - adm
    - remove_groups: False

/usr/lib/nagios/plugins/check_php_fpm.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_php_fpm.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/php-fpm.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/php-fpm.cfg.jinja
    - template: jinja
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_php_fpm.sh
    - watch_in:
      - service: nagios-nrpe-server

/usr/lib/nagios/plugins/check_php_errors.sh:
  file.managed:
    - source: salt://monitoring/files/nrpe/check_php_errors.sh
    - mode: '0755'
    - user: root
    - group: root

/etc/nagios/nrpe.d/php-errors.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/php-errors.cfg.jinja
    - template: jinja
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_php_errors.sh
    - watch_in:
      - service: nagios-nrpe-server
