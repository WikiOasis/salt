git:
  pkg.installed: []

mediawiki-services-jobrunner:
  git.latest:
    - name: https://github.com/wikimedia/mediawiki-services-jobrunner
    - target: /srv/mediawiki-services-jobrunner
    - user: root
    - require:
      - pkg: git

/etc/mediawiki-jobrunner:
  file.directory:
    - user: root
    - group: www-data
    - mode: '0750'

/etc/mediawiki-jobrunner/config.json:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/config.json.jinja
    - template: jinja
    - user: root
    - group: www-data
    - mode: '0640'
    - require:
      - file: /etc/mediawiki-jobrunner

/etc/systemd/system/mediawiki-jobrunner.service:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/mediawiki-jobrunner.service
    - user: root
    - group: root
    - mode: '0644'

/etc/systemd/system/mediawiki-jobchron.service:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/mediawiki-jobchron.service
    - user: root
    - group: root
    - mode: '0644'

mediawiki-jobrunner:
  service.running:
    - enable: True
    - watch:
      - git: mediawiki-services-jobrunner
      - file: /etc/mediawiki-jobrunner/config.json
      - file: /etc/systemd/system/mediawiki-jobrunner.service

mediawiki-jobchron:
  service.running:
    - enable: True
    - watch:
      - git: mediawiki-services-jobrunner
      - file: /etc/mediawiki-jobrunner/config.json
      - file: /etc/systemd/system/mediawiki-jobchron.service
