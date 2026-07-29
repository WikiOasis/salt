{%- set token = salt['pillar.get']('monitoring:cloudflare_exporter_token') %}

# No Debian package or release binary exists for this exporter (only a Docker
# image is published upstream), so it's installed from PyPI into its own venv.
# (ID can't be "prometheus_user" - that's already declared by statsd_exporter.sls,
# and SLS IDs must be globally unique across every state applied to a minion.)
cloudflare_exporter_prometheus_user:
  user.present:
    - name: prometheus
    - system: True
    - shell: /usr/sbin/nologin
    - home: /var/lib/prometheus
    - createhome: False

cloudflare_exporter_deps:
  pkg.installed:
    - pkgs:
      - python3-venv
      - python3-pip

cloudflare_exporter_venv:
  cmd.run:
    - name: python3 -m venv /opt/cloudflare_exporter
    - creates: /opt/cloudflare_exporter/bin/python3
    - require:
      - pkg: cloudflare_exporter_deps

cloudflare_exporter_install:
  cmd.run:
    - name: /opt/cloudflare_exporter/bin/pip install cloudflare-exporter==0.7
    - unless: "/opt/cloudflare_exporter/bin/pip show cloudflare-exporter 2>/dev/null | grep -q '^Version: 0.7$'"
    - require:
      - cmd: cloudflare_exporter_venv

/etc/prometheus:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - makedirs: True

/etc/prometheus/cloudflare_exporter.env:
  file.managed:
    - contents: |
        CF_API_TOKEN={{ token }}
    - user: root
    - group: prometheus
    - mode: '0640'
    - require:
      - file: /etc/prometheus

/etc/systemd/system/prometheus-cloudflare-exporter.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Prometheus Cloudflare Exporter
        After=network.target

        [Service]
        User=prometheus
        EnvironmentFile=/etc/prometheus/cloudflare_exporter.env
        ExecStart=/opt/cloudflare_exporter/bin/run-app --token ${CF_API_TOKEN} --host 0.0.0.0 --port 9199
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - cmd: cloudflare_exporter_install

prometheus-cloudflare-exporter:
  service.running:
    - enable: True
    - watch:
      - file: /etc/prometheus/cloudflare_exporter.env
      - file: /etc/systemd/system/prometheus-cloudflare-exporter.service
    - require:
      - user: cloudflare_exporter_prometheus_user
      - cmd: cloudflare_exporter_install
      - file: /etc/systemd/system/prometheus-cloudflare-exporter.service
