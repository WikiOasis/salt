# Vector ships journald (all units) and nginx logs to Sentry, routed through the
# local sentry-relay on 127.0.0.1:3030. nginx and journald use separate DSNs and
# each event is tagged with its originating unit/system. See sentry_relay state.

vector_user:
  user.present:
    - name: vector
    - system: True
    - shell: /usr/sbin/nologin
    - home: /var/lib/vector
    - createhome: False
    # systemd-journal: read the journal. adm: read /var/log/nginx/*.log.
    - groups:
      - systemd-journal
      - adm

/var/lib/vector:
  file.directory:
    - user: vector
    - group: vector
    - mode: '0750'
    - require:
      - user: vector_user

/etc/vector:
  file.directory:
    - user: root
    - group: vector
    - mode: '0750'
    - require:
      - user: vector_user

vector_binary:
  archive.extracted:
    - name: /opt/vector
    - source: https://github.com/vectordotdev/vector/releases/download/v0.56.0/vector-0.56.0-x86_64-unknown-linux-gnu.tar.gz
    - source_hash: https://github.com/vectordotdev/vector/releases/download/v0.56.0/vector-0.56.0-SHA256SUMS
    - archive_format: tar
    - options: '--strip-components=2'
    - enforce_toplevel: False
    - if_missing: /opt/vector/bin/vector

/usr/local/bin/vector:
  file.symlink:
    - target: /opt/vector/bin/vector
    - require:
      - archive: vector_binary

/etc/vector/vector.toml:
  file.managed:
    - source: salt://monitoring/files/vector/vector.toml.jinja
    - template: jinja
    - user: root
    - group: vector
    - mode: '0640'
    - require:
      - file: /etc/vector

/etc/systemd/system/vector.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Vector log shipper
        After=network-online.target
        Wants=network-online.target

        [Service]
        User=vector
        Group=vector
        ExecStart=/usr/local/bin/vector --config /etc/vector/vector.toml
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

vector:
  service.running:
    - enable: True
    - watch:
      - file: /etc/vector/vector.toml
      - file: /etc/systemd/system/vector.service
    - require:
      - file: /usr/local/bin/vector
      - file: /etc/vector/vector.toml
      - file: /var/lib/vector
      - file: /etc/systemd/system/vector.service
      - user: vector_user
