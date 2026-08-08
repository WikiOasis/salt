{%- set backup = salt['pillar.get']('mariadb:backup', {}) %}
{%- set s3 = backup.get('s3', {}) %}
{%- set schedule = backup.get('schedule', {}) %}
{%- if backup and s3.get('bucket') %}

mariadb_backup_pkgs:
  pkg.installed:
    - pkgs:
      - mariadb-backup
      - awscli
      - jq
      - curl
      - zstd
      - pv

/etc/mariadb-backup:
  file.directory:
    - user: root
    - group: root
    - mode: '0750'

/etc/mariadb-backup/s3.env:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-s3.env.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/mariadb-backup

/etc/mariadb-backup/credentials:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-credentials.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0600'
    - show_changes: False
    - require:
      - file: /etc/mariadb-backup

/etc/mariadb-backup/aws.conf:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-aws.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/mariadb-backup

/etc/mariadb-backup/lifecycle.json:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-lifecycle.json.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0640'
    - require:
      - file: /etc/mariadb-backup

# The SSH destination is gone; the key it used is dead weight on disk.
/etc/mariadb-backup/ssh_key:
  file.absent

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

/usr/local/bin/mariadb-backup-s3-init.sh:
  file.managed:
    - source: salt://mariadb/files/mariadb-backup-s3-init.sh
    - user: root
    - group: root
    - mode: '0750'

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

# Retention lives in the bucket, not in the scripts: objects transition to the
# Infrequent Access storage class and expire from there. `--check` compares the
# live policy against the rendered one, so this is a no-op once applied and
# re-applies itself if the pillar changes or someone edits it in the console.
mariadb_backup_s3_lifecycle:
  cmd.run:
    - name: /usr/local/bin/mariadb-backup-s3-init.sh
    - unless: /usr/local/bin/mariadb-backup-s3-init.sh --check
    - require:
      - pkg: mariadb_backup_pkgs
      - file: /usr/local/bin/mariadb-backup-s3-init.sh
      - file: /etc/mariadb-backup/s3.env
      - file: /etc/mariadb-backup/credentials
      - file: /etc/mariadb-backup/aws.conf
      - file: /etc/mariadb-backup/lifecycle.json

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

# Sync binlogs to the bucket every 5 minutes
mariadb_binlog_sync_cron:
  cron.present:
    - name: /usr/local/bin/mariadb-binlog-sync.sh >> /var/log/mariadb-backup.log 2>&1
    - user: root
    - minute: '*/5'
    - identifier: mariadb-binlog-sync

{%- endif %}
