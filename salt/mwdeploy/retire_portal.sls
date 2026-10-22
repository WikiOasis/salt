{%- set php_version = '8.4' %}

mwdeploy-portal-services:
  service.dead:
    - names:
      - mwdeploy-worker
      - mwdeploy-reverb
    - enable: False

mwdeploy-portal-units:
  file.absent:
    - names:
      - /etc/systemd/system/mwdeploy-worker.service
      - /etc/systemd/system/mwdeploy-reverb.service
    - require:
      - service: mwdeploy-portal-services

mwdeploy-portal-daemon-reload:
  cmd.run:
    - name: systemctl daemon-reload
    - onchanges:
      - file: mwdeploy-portal-units

mwdeploy-portal-web:
  file.absent:
    - names:
      - /etc/nginx/conf.d/deploy-portal.conf
      - /etc/php/{{ php_version }}/fpm/pool.d/deploy-portal.conf

mwdeploy-portal-web-services:
  service.dead:
    - names:
      - nginx
      - php{{ php_version }}-fpm
    - enable: False
    - onchanges:
      - file: mwdeploy-portal-web

/srv/deploy-portal:
  file.absent:
    - require:
      - service: mwdeploy-portal-services

/etc/salt/master.d/mwdeploy-acl.conf:
  file.absent: []

mwdeploy-portal-salt-group:
  group.present:
    - name: salt
    - system: True
    - delusers:
      - www-data

mwdeploy-portal-salt-master:
  service.running:
    - name: salt-master
    - enable: True
    - watch:
      - file: /etc/salt/master.d/mwdeploy-acl.conf
