{%- set p = salt['pillar.get']('fandom_import', {}) %}
{%- set spool = p.get('spool_dir', '/srv/fandom-import') %}
{%- set venv = p.get('venv', '/opt/fandom-import/venv') %}
{%- set version = p.get('wikiteam3_version', '4.4.10') %}
{%- set proxy = p.get('proxy', 'http://10.0.1.1:3129') %}
{%- set worker = '/opt/fandom-import/fandom_import_worker.py' %}
{%- set config = '/etc/fandom-import/config.json' %}

fandom_import_pkgs:
  pkg.installed:
    - pkgs:
      - p7zip-full
      - python3-venv
      - python3-pip
      - logrotate

/opt/fandom-import:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

fandom_import_venv:
  cmd.run:
    - name: python3 -m venv {{ venv }}
    - creates: {{ venv }}/bin/python3
    - require:
      - pkg: fandom_import_pkgs
      - file: /opt/fandom-import

fandom_import_wikiteam3:
  cmd.run:
    - name: {{ venv }}/bin/pip install --proxy {{ proxy }} wikiteam3=={{ version }}
    - unless: "{{ venv }}/bin/pip show wikiteam3 2>/dev/null | grep -q '^Version: {{ version }}$'"
    - require:
      - cmd: fandom_import_venv

{{ worker }}:
  file.managed:
    - source: salt://fandom_import/files/fandom_import_worker.py
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: /opt/fandom-import

/etc/fandom-import:
  file.directory:
    - user: root
    - group: www-data
    - mode: '0750'

{{ config }}:
  file.managed:
    - source: salt://fandom_import/files/config.json.jinja
    - template: jinja
    - user: root
    - group: www-data
    - mode: '0640'
    - require:
      - file: /etc/fandom-import

fandom_import_spool:
  file.directory:
    - names:
      - {{ spool }}
      - {{ spool }}/queue
      - {{ spool }}/work
      - {{ spool }}/logs
      - {{ spool }}/tmp
    - user: www-data
    - group: www-data
    - mode: '0750'
    - makedirs: True

fandom_import_worker_cron:
  cron.present:
    - name: {{ venv }}/bin/python {{ worker }} --config {{ config }} run >> {{ spool }}/logs/worker.log 2>&1
    - user: www-data
    - minute: '*'
    - identifier: fandom-import-worker
    - require:
      - pkg: fandom_import_pkgs
      - cmd: fandom_import_wikiteam3
      - file: {{ worker }}
      - file: {{ config }}
      - file: fandom_import_spool

fandom_import_janitor_cron:
  cron.present:
    - name: {{ venv }}/bin/python {{ worker }} --config {{ config }} janitor >> {{ spool }}/logs/worker.log 2>&1
    - user: www-data
    - minute: '23'
    - hour: '4'
    - identifier: fandom-import-janitor
    - require:
      - cmd: fandom_import_wikiteam3
      - file: {{ worker }}
      - file: {{ config }}
      - file: fandom_import_spool

/etc/logrotate.d/fandom-import:
  file.managed:
    - contents: |
        {{ spool }}/logs/worker.log {
            weekly
            rotate 4
            compress
            missingok
            notifempty
            copytruncate
            su www-data www-data
        }
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: fandom_import_pkgs
