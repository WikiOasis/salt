sentry_relay_user:
  user.present:
    - name: sentry-relay
    - system: True
    - shell: /usr/sbin/nologin
    - home: /var/lib/sentry-relay
    - createhome: False

/etc/sentry-relay:
  file.directory:
    - user: sentry-relay
    - group: sentry-relay
    - mode: '0750'
    - require:
      - user: sentry_relay_user

/var/lib/sentry-relay:
  file.directory:
    - user: sentry-relay
    - group: sentry-relay
    - mode: '0750'
    - require:
      - user: sentry_relay_user

sentry_relay_binary:
  file.managed:
    - name: /usr/local/bin/sentry-relay
    - source: https://github.com/getsentry/relay/releases/download/24.9.0/relay-Linux-x86_64
    - source_hash: https://github.com/getsentry/relay/releases/download/24.9.0/relay-Linux-x86_64.sha256
    - mode: '0755'
    - user: root
    - group: root

/etc/sentry-relay/config.yml:
  file.managed:
    - source: salt://sentry_relay/files/config.yml.jinja
    - template: jinja
    - user: sentry-relay
    - group: sentry-relay
    - mode: '0640'
    - require:
      - file: /etc/sentry-relay

/etc/systemd/system/sentry-relay.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Sentry Relay
        After=network.target

        [Service]
        User=sentry-relay
        WorkingDirectory=/var/lib/sentry-relay
        ExecStart=/usr/local/bin/sentry-relay run --config /etc/sentry-relay
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

sentry-relay:
  service.running:
    - enable: True
    - watch:
      - file: /etc/sentry-relay/config.yml
    - require:
      - user: sentry_relay_user
      - file: sentry_relay_binary
      - file: /etc/sentry-relay/config.yml
      - file: /var/lib/sentry-relay
      - file: /etc/systemd/system/sentry-relay.service
