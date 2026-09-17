{%- set admin_user = salt['pillar.get']('monitoring:grafana:admin_user', 'admin') %}
{%- set admin_pass = salt['pillar.get']('monitoring:grafana_admin_password') %}

grafana_apt_key:
  cmd.run:
    - name: >-
        curl -fsSL https://packages.grafana.com/gpg.key |
        gpg --dearmor -o /usr/share/keyrings/grafana-archive-keyring.gpg
    - creates: /usr/share/keyrings/grafana-archive-keyring.gpg

/etc/apt/sources.list.d/grafana.list:
  file.managed:
    - contents: |
        deb [signed-by=/usr/share/keyrings/grafana-archive-keyring.gpg] https://packages.grafana.com/oss/deb stable main
    - require:
      - cmd: grafana_apt_key

grafana_apt_update:
  cmd.run:
    - name: apt-get update -qq
    - onchanges:
      - file: /etc/apt/sources.list.d/grafana.list

grafana_pkg:
  pkg.installed:
    - name: grafana
    - require:
      - cmd: grafana_apt_update

/etc/grafana/grafana.ini:
  file.managed:
    - source: salt://monitoring/files/grafana/grafana.ini.jinja
    - template: jinja
    - user: root
    - group: grafana
    - mode: '0640'
    - context:
        admin_user: {{ admin_user }}
        admin_pass: {{ admin_pass }}
    - require:
      - pkg: grafana_pkg
    - watch_in:
      - service: grafana-server

/etc/grafana/provisioning/datasources/prometheus.yml:
  file.managed:
    - source: salt://monitoring/files/grafana/datasource.yml.jinja
    - template: jinja
    - user: root
    - group: grafana
    - mode: '0640'
    - makedirs: True
    - require:
      - pkg: grafana_pkg
    - watch_in:
      - service: grafana-server

/etc/grafana/provisioning/dashboards/salt.yml:
  file.managed:
    - source: salt://monitoring/files/grafana/dashboards.yml.jinja
    - template: jinja
    - user: root
    - group: grafana
    - mode: '0640'
    - makedirs: True
    - require:
      - pkg: grafana_pkg
    - watch_in:
      - service: grafana-server

# The provider above polls this directory every 60s, so a changed dashboard is
# picked up without restarting Grafana. It is owned by grafana rather than root
# because the provisioner reads it as the grafana user.
/var/lib/grafana/dashboards:
  file.recurse:
    - source: salt://monitoring/files/grafana/dashboards
    - user: grafana
    - group: grafana
    - dir_mode: '0750'
    - file_mode: '0640'
    - clean: True
    - makedirs: True
    - require:
      - pkg: grafana_pkg

/etc/nginx/sites-available/grafana.conf:
  file.managed:
    - source: salt://monitoring/files/nginx/grafana.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: grafana_pkg

/etc/nginx/sites-enabled/grafana.conf:
  file.symlink:
    - target: /etc/nginx/sites-available/grafana.conf
    - require:
      - file: /etc/nginx/sites-available/grafana.conf
    - watch_in:
      - service: nginx

grafana-server:
  service.running:
    - enable: True
    - require:
      - pkg: grafana_pkg