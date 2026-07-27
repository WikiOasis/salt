# rsync daemon on the staging host, exporting the production tree for
# mw*/task* appservers to pull from. See mw-deploy's docs/SALT-INTEGRATION.md
# section 5 and docs/OPERATIONS.md "Getting bits from staging to the appservers".
#
# Exports /srv/mediawiki (production on staging), not /srv/mediawiki-staging:
# the pipeline is git checkout -> staging tree -> rsync-local staging->production
# on this host -> appservers pull that production tree. This module IS the
# canonical artefact and must not be world-readable.

rsync:
  pkg.installed: []

/etc/rsyncd.conf:
  file.managed:
    - contents: |
        uid = www-data
        gid = www-data
        use chroot = yes
        max connections = 16
        read only = yes
        log file = /var/log/rsyncd.log

        [mediawiki]
            path = /srv/mediawiki
            comment = Staged MediaWiki tree for appserver pulls
            hosts allow = 10.0.0.0/8
            hosts deny = *
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: rsync

rsync_service:
  service.running:
    - name: rsync
    - enable: True
    - watch:
      - file: /etc/rsyncd.conf
    - require:
      - pkg: rsync
