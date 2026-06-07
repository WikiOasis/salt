{%- set backup = salt['pillar.get']('mariadb:backup', {}) %}
{%- set dest = backup.get('destination', {}) %}
{%- set schedule = backup.get('schedule', {}) %}
{%- if backup and dest.get('host') %}

mariadb_backup_pkgs:
  pkg.installed:
    - pkgs:
      - mariadb-backup
      - jq
      - curl
      - zstd

/etc/mariadb-backup:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'

/etc/mariadb-backup/ssh_key:
  file.managed:
    - contents_pillar: mariadb:backup:ssh_private_key
    - user: root
    - group: root
    - mode: '0600'
    - require:
      - file: /etc/mariadb-backup

/var/backups/mariadb:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'
    - makedirs: True

/var/backups/mariadb/binlogs:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'
    - require:
      - file: /var/backups/mariadb

/usr/local/bin/mariadb-backup-run.sh:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-run.sh.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0750'

/usr/local/bin/mariadb-binlog-stream.sh:
  file.managed:
    - source: salt://mariadb/files/mariadb-binlog-stream.sh.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0750'

/usr/local/bin/mariadb-binlog-sync.sh:
  file.managed:
    - source: salt://mariadb/files/mariadb-binlog-sync.sh.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0750'

/etc/systemd/system/mariadb-binlog-stream.service:
  file.managed:
    - source: salt://mariadb/files/mariadb-binlog-stream.service
    - user: root
    - group: root
    - mode: '0644'

mariadb-binlog-stream:
  service.running:
    - enable: True
    - require:
      - file: /etc/systemd/system/mariadb-binlog-stream.service
      - file: /usr/local/bin/mariadb-binlog-stream.sh
      - file: /var/backups/mariadb/binlogs
      - pkg: install_mariadb
      - pkg: mariadb_backup_pkgs
    - watch:
      - file: /etc/systemd/system/mariadb-binlog-stream.service
      - file: /usr/local/bin/mariadb-binlog-stream.sh

mariadb_backup_db_user:
  cmd.run:
    - name: >
        mysql -e
        "CREATE USER IF NOT EXISTS '{{ backup.get('user', 'mariadb_backup') }}'@'localhost' IDENTIFIED BY '{{ backup.get('password', '') }}';
        ALTER USER '{{ backup.get('user', 'mariadb_backup') }}'@'localhost' IDENTIFIED BY '{{ backup.get('password', '') }}';
        GRANT RELOAD, LOCK TABLES, PROCESS, REPLICATION CLIENT, REPLICATION SLAVE ON *.* TO '{{ backup.get('user', 'mariadb_backup') }}'@'localhost';
        FLUSH PRIVILEGES;"
    - require:
      - pkg: install_mariadb
      - service: mariadb

# Weekly full backup on Sunday (default 01:00, overridable per host via pillar)
mariadb_backup_weekly_cron:
  cron.present:
    - name: /usr/local/bin/mariadb-backup-run.sh full >> /var/log/mariadb-backup.log 2>&1
    - user: root
    - minute: '{{ schedule.get('full_minute', '0') }}'
    - hour: '{{ schedule.get('full_hour', '1') }}'
    - dayweek: '0'
    - identifier: mariadb-backup-weekly

# Daily incremental backup Mon-Sat (default 02:00, overridable per host via pillar)
mariadb_backup_daily_cron:
  cron.present:
    - name: /usr/local/bin/mariadb-backup-run.sh incremental >> /var/log/mariadb-backup.log 2>&1
    - user: root
    - minute: '{{ schedule.get('incremental_minute', '0') }}'
    - hour: '{{ schedule.get('incremental_hour', '2') }}'
    - dayweek: '1-6'
    - identifier: mariadb-backup-daily

# Sync binlogs to remote every 5 minutes
mariadb_binlog_sync_cron:
  cron.present:
    - name: /usr/local/bin/mariadb-binlog-sync.sh >> /var/log/mariadb-backup.log 2>&1
    - user: root
    - minute: '*/5'
    - identifier: mariadb-binlog-sync

{%- endif %}
