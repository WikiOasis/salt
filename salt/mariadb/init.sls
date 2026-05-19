install_mariadb:
  pkg.installed:
    - name: mariadb-server

/etc/mysql/mariadb.conf.d/50-server.cnf:
  file.managed:
    - source: salt://mariadb/files/50-server.cnf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: install_mariadb

mariadb:
  service.running:
    - enable: True
    - watch:
      - file: /etc/mysql/mariadb.conf.d/50-server.cnf