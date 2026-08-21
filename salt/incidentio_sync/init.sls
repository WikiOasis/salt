# Mirrors the incident.io status page into a Discord channel via webhook
# (https://github.com/WikiOasis/incidentio-sync). Pure stdlib Python 3.9+, no
# packages to install. Runs as a long-lived daemon (Type=simple, internal 15s
# poll loop) rather than the repo's alternative timer+oneshot mode, which would
# spawn a fresh interpreter every 15 seconds for the same result.
#
# It polls the rendered status page rather than the Atom feed, so it can see
# components that are healthy (needed for the sticky overview message) and each
# incident's full update timeline.
#
# state.json under /var/lib/incidentio-sync maps incidents to Discord message
# IDs — it is runtime data, not configuration. Salt manages the directory
# (StateDirectory= on the unit would create it anyway) but must NEVER touch
# the file itself: templating or removing it makes the service repost every
# incident as a brand-new message, and orphan the sticky overview.

incidentio_sync_user:
  user.present:
    - name: incidentio-sync
    - system: True
    - shell: /usr/sbin/nologin
    - home: /opt/incidentio-sync
    - createhome: False

/opt/incidentio-sync:
  file.directory:
    - user: incidentio-sync
    - group: incidentio-sync
    - mode: '0755'
    - require:
      - user: incidentio_sync_user

# Not managed with recurse/clean, and state.json is never referenced here —
# ownership only, so an existing state.json is left untouched.
/var/lib/incidentio-sync:
  file.directory:
    - user: incidentio-sync
    - group: incidentio-sync
    - mode: '0750'
    - require:
      - user: incidentio_sync_user

/opt/incidentio-sync/incidentio_sync.py:
  file.managed:
    - source: salt://incidentio_sync/files/incidentio_sync.py
    - user: incidentio-sync
    - group: incidentio-sync
    - mode: '0755'
    - require:
      - file: /opt/incidentio-sync

/etc/incidentio-sync.env:
  file.managed:
    - source: salt://incidentio_sync/files/incidentio-sync.env.jinja
    - template: jinja
    - user: incidentio-sync
    - group: incidentio-sync
    - mode: '0600'
    - show_changes: False
    - require:
      - user: incidentio_sync_user

/etc/systemd/system/incidentio-sync-daemon.service:
  file.managed:
    - contents: |
        [Unit]
        Description=Sync incident.io status feed to a Discord webhook (long-running)
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        User=incidentio-sync
        WorkingDirectory=/opt/incidentio-sync
        EnvironmentFile=/etc/incidentio-sync.env
        # POLL_INTERVAL must be set (e.g. 15) for daemon mode; without it the
        # process does one pass and exits, which systemd would then restart in
        # a tight loop. Asserted here too, redundantly, in case the env file
        # value is ever missing.
        Environment=POLL_INTERVAL=15
        ExecStart=/usr/bin/python3 -u /opt/incidentio-sync/incidentio_sync.py
        Restart=always
        RestartSec=10s

        StateDirectory=incidentio-sync
        NoNewPrivileges=true
        PrivateTmp=true
        ProtectSystem=strict
        ProtectHome=true
        ProtectKernelTunables=true
        ProtectControlGroups=true
        RestrictAddressFamilies=AF_INET AF_INET6
        RestrictNamespaces=true
        MemoryDenyWriteExecute=true

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

incidentio-sync-daemon:
  service.running:
    - enable: True
    - watch:
      - file: /opt/incidentio-sync/incidentio_sync.py
      - file: /etc/incidentio-sync.env
      - file: /etc/systemd/system/incidentio-sync-daemon.service
    - require:
      - user: incidentio_sync_user
      - file: /opt/incidentio-sync/incidentio_sync.py
      - file: /etc/incidentio-sync.env
      - file: /var/lib/incidentio-sync
      - file: /etc/systemd/system/incidentio-sync-daemon.service
