install_mariadb:
  pkg.installed:
    - name: mariadb-server

/var/log/mysql:
  file.directory:
    - user: mysql
    - group: adm
    - mode: '2750'
    - require:
      - pkg: install_mariadb

/etc/mysql/mariadb.conf.d/50-server.cnf:
  file.managed:
    - source: salt://mariadb/files/50-server.cnf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: install_mariadb

# bind-address is the vRack IP, which must exist before mariadbd starts.
/etc/systemd/system/mariadb.service.d/network-online.conf:
  file.managed:
    - makedirs: True
    - user: root
    - group: root
    - mode: '0644'
    - contents: |
        [Unit]
        Wants=network-online.target
        After=network-online.target
    - require:
      - pkg: install_mariadb

mariadb:
  service.running:
    - enable: True
    - require:
      - file: /var/log/mysql
    - watch:
      - file: /etc/mysql/mariadb.conf.d/50-server.cnf
      - file: /etc/systemd/system/mariadb.service.d/network-online.conf