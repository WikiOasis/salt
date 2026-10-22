mwdeploy-rsyncd-retired:
  service.dead:
    - name: rsync
    - enable: False

/etc/rsyncd.conf:
  file.absent:
    - require:
      - service: mwdeploy-rsyncd-retired
