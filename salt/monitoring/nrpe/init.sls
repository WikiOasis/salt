nrpe_packages:
  pkg.installed:
    - pkgs:
      - nagios-nrpe-server
      - nagios-plugins-basic
      - nagios-plugins-standard
      - nagios-plugins-contrib

/etc/nagios/nrpe.cfg:
  file.managed:
    - source: salt://monitoring/nrpe/files/nrpe.cfg.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - require:
      - pkg: nrpe_packages

nagios-nrpe-server:
  service.running:
    - enable: True
    - watch:
      - file: /etc/nagios/nrpe.cfg
    - require:
      - pkg: nrpe_packages
