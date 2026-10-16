{%- set sal = salt['pillar.get']('sal', {}) %}
{%- set missing = [] %}
{%- for key in ['secret', 'db_password'] if not sal.get(key) %}{%- do missing.append('sal:' ~ key) %}{%- endfor %}
{%- if sal.get('wiki', {}).get('enabled', True) and not (sal.get('wiki', {}).get('user') and sal.get('wiki', {}).get('password')) %}{%- do missing.append('sal:wiki:user/password') %}{%- endif %}
{%- if sal.get('phorge', {}).get('enabled', True) and not sal.get('phorge', {}).get('token') %}{%- do missing.append('sal:phorge:token') %}{%- endif %}

include:
  - sal.client

{%- if missing %}
sal-server-secrets-missing:
  test.fail_without_changes:
    - name: "missing pillar for sal-server: {{ missing | join(', ') }}"
{%- endif %}

sal-server-deps:
  pkg.installed:
    - pkgs:
      - python3
      - python3-pymysql

sal-server-user:
  user.present:
    - name: sal
    - system: True
    - gid: sal
    - shell: /usr/sbin/nologin
    - home: /opt/sal
    - createhome: False
    - require:
      - group: sal-group

/opt/sal:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/opt/sal/sal_server.py:
  file.managed:
    - source: salt://sal/files/sal_server.py
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: /opt/sal

/etc/sal/server.env:
  file.managed:
    - source: salt://sal/files/sal-server.env.jinja
    - template: jinja
    - user: sal
    - group: sal
    - mode: '0600'
    - show_changes: False
    - require:
      - user: sal-server-user
      - file: /etc/sal

/etc/systemd/system/sal-server.service:
  file.managed:
    - contents: |
        [Unit]
        Description=WikiOasis server admin log
        After=network-online.target
        Wants=network-online.target
        StartLimitIntervalSec=10min
        StartLimitBurst=10

        [Service]
        Type=simple
        User=sal
        Group=sal
        EnvironmentFile=/etc/sal/server.env
        ExecStart=/usr/bin/python3 -u /opt/sal/sal_server.py
        Restart=always
        RestartSec=10s

        NoNewPrivileges=true
        PrivateTmp=true
        ProtectSystem=strict
        ProtectHome=true
        ProtectKernelTunables=true
        ProtectControlGroups=true
        RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
        RestrictNamespaces=true
        MemoryDenyWriteExecute=true

        [Install]
        WantedBy=multi-user.target
    - user: root
    - group: root
    - mode: '0644'

sal-server:
  service.running:
    - enable: True
    - watch:
      - file: /opt/sal/sal_server.py
      - file: /etc/sal/server.env
      - file: /etc/systemd/system/sal-server.service
    - require:
      - pkg: sal-server-deps
      - user: sal-server-user
