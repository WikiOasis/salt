{%- set jr = salt['pillar.get']('mediawiki_jobrunner', {}) %}
{%- set workers = jr.get('workers', 4) %}

/etc/mediawiki-jobrunner:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/etc/mediawiki-jobrunner/config.yaml:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/config.yaml.jinja
    - template: jinja
    - user: root
    - group: www-data
    - mode: '0640'
    - require:
      - file: /etc/mediawiki-jobrunner

/usr/local/bin/mediawiki-jobrunner:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/mediawiki-jobrunner
    - user: root
    - group: root
    - mode: '0755'

/etc/systemd/system/mediawiki-jobrunner@.service:
  file.managed:
    - source: salt://mediawiki/jobrunner/files/mediawiki-jobrunner@.service
    - user: root
    - group: root
    - mode: '0644'

{%- for i in range(1, workers + 1) %}
mediawiki-jobrunner@{{ i }}:
  service.running:
    - enable: True
    - watch:
      - file: /etc/mediawiki-jobrunner/config.yaml
      - file: /etc/systemd/system/mediawiki-jobrunner@.service
      - file: /usr/local/bin/mediawiki-jobrunner
{%- endfor %}
