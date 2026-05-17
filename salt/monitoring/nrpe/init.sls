nrpe_apt_fix_broken:
  cmd.run:
    - name: DEBIAN_FRONTEND=noninteractive apt-get install -f -y
    - onlyif: dpkg --audit | grep -q .

nrpe_packages:
  pkg.installed:
    - pkgs:
      - nagios-nrpe-server
      - monitoring-plugins-basic
      - monitoring-plugins-standard
      - monitoring-plugins-contrib
    - require:
      - cmd: nrpe_apt_fix_broken

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
