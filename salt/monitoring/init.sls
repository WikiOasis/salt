# Icinga doesn't publish an icinga-trixie repo yet; bookworm packages work fine on Debian 13.
{%- set icinga_dist = 'icinga-bookworm' if grains['oscodename'] == 'trixie' else 'icinga-' + grains['oscodename'] %}

{%- set ido_db      = salt['pillar.get']('monitoring:ido_db_name',      'icinga2') %}
{%- set ido_user    = salt['pillar.get']('monitoring:ido_db_user',      'icinga2') %}
{%- set ido_pass    = salt['pillar.get']('monitoring:ido_db_password') %}
{%- set dir_db      = salt['pillar.get']('monitoring:director_db_name', 'icinga_director') %}
{%- set dir_user    = salt['pillar.get']('monitoring:director_db_user', 'icinga_director') %}
{%- set dir_pass    = salt['pillar.get']('monitoring:director_db_password') %}

# ── Icinga apt repository ──────────────────────────────────────────────────────

icinga_apt_key:
  cmd.run:
    - name: >-
        curl -fsSL https://packages.icinga.com/icinga.key |
        gpg --dearmor -o /usr/share/keyrings/icinga-archive-keyring.gpg
    - creates: /usr/share/keyrings/icinga-archive-keyring.gpg

/etc/apt/sources.list.d/icinga.list:
  file.managed:
    - contents: |
        deb [signed-by=/usr/share/keyrings/icinga-archive-keyring.gpg] https://packages.icinga.com/debian {{ icinga_dist }} main
    - require:
      - cmd: icinga_apt_key

icinga_apt_update:
  cmd.run:
    - name: apt-get update -qq
    - require:
      - file: /etc/apt/sources.list.d/icinga.list
      - cmd: icinga_apt_key

# ── Packages ──────────────────────────────────────────────────────────────────

monitoring_apt_fix_broken:
  cmd.run:
    - name: DEBIAN_FRONTEND=noninteractive apt-get install -f -y
    - onlyif: dpkg --audit | grep -q .
    - require:
      - cmd: icinga_apt_update

monitoring_packages:
  pkg.installed:
    - pkgs:
      - icinga2
      - icinga2-ido-mysql
      - icingaweb2
      - icingacli
      - icinga-director
      - mariadb-server
      - mariadb-client
      - nginx
      - php-fpm
      - php-mysql
      - php-intl
      - php-curl
      - php-gd
      - php-mbstring
      - php-xml
      - nagios-nrpe-plugin
      - jq
      - curl
    - require:
      - cmd: monitoring_apt_fix_broken

# ── Local MariaDB databases ────────────────────────────────────────────────────

mariadb_running:
  service.running:
    - name: mariadb
    - enable: True
    - require:
      - pkg: monitoring_packages

monitoring_db_ido:
  cmd.run:
    - name: |
        mysql -e "
          CREATE DATABASE IF NOT EXISTS {{ ido_db }} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
          CREATE USER IF NOT EXISTS '{{ ido_user }}'@'localhost' IDENTIFIED BY '{{ ido_pass }}';
          GRANT ALL ON {{ ido_db }}.* TO '{{ ido_user }}'@'localhost';"
    - require:
      - service: mariadb_running

monitoring_db_director:
  cmd.run:
    - name: |
        mysql -e "
          CREATE DATABASE IF NOT EXISTS {{ dir_db }} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
          CREATE USER IF NOT EXISTS '{{ dir_user }}'@'localhost' IDENTIFIED BY '{{ dir_pass }}';
          GRANT ALL ON {{ dir_db }}.* TO '{{ dir_user }}'@'localhost';"
    - require:
      - service: mariadb_running

import_ido_schema:
  cmd.run:
    - name: >-
        mysql {{ ido_db }} < /usr/share/icinga2-ido-mysql/schema/mysql.sql &&
        touch /etc/icinga2/.ido_schema_imported
    - creates: /etc/icinga2/.ido_schema_imported
    - require:
      - cmd: monitoring_db_ido

# ── Icinga2 configuration ──────────────────────────────────────────────────────

/etc/icinga2/zones.conf:
  file.managed:
    - source: salt://monitoring/files/icinga2/zones.conf.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - require:
      - pkg: monitoring_packages

/etc/icinga2/features-available/api.conf:
  file.managed:
    - source: salt://monitoring/files/icinga2/api.conf.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - require:
      - pkg: monitoring_packages

/etc/icinga2/features-available/ido-mysql.conf:
  file.managed:
    - source: salt://monitoring/files/icinga2/ido-mysql.conf.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - require:
      - cmd: import_ido_schema

icinga2_feature_api:
  cmd.run:
    - name: icinga2 feature enable api
    - creates: /etc/icinga2/features-enabled/api.conf
    - require:
      - file: /etc/icinga2/features-available/api.conf

icinga2_feature_ido_mysql:
  cmd.run:
    - name: icinga2 feature enable ido-mysql
    - creates: /etc/icinga2/features-enabled/ido-mysql.conf
    - require:
      - file: /etc/icinga2/features-available/ido-mysql.conf

icinga2_feature_notification:
  cmd.run:
    - name: icinga2 feature enable notification
    - creates: /etc/icinga2/features-enabled/notification.conf
    - require:
      - pkg: monitoring_packages

icinga2:
  service.running:
    - enable: True
    - watch:
      - file: /etc/icinga2/zones.conf
      - file: /etc/icinga2/features-available/api.conf
      - file: /etc/icinga2/features-available/ido-mysql.conf
    - require:
      - cmd: icinga2_feature_api
      - cmd: icinga2_feature_ido_mysql
      - cmd: icinga2_feature_notification

# ── Notification scripts ───────────────────────────────────────────────────────

/etc/icinga2/scripts:
  file.directory:
    - user: root
    - group: nagios
    - mode: '0750'
    - require:
      - pkg: monitoring_packages

/etc/icinga2/scripts/webhook_config.sh:
  file.managed:
    - source: salt://monitoring/files/notify/webhook_config.sh.jinja
    - template: jinja
    - user: root
    - group: nagios
    - mode: '0640'
    - require:
      - file: /etc/icinga2/scripts

{%- for script in ['discord_host', 'discord_service', 'slack_host', 'slack_service'] %}
/etc/icinga2/scripts/{{ script }}_notification.sh:
  file.managed:
    - source: salt://monitoring/files/notify/{{ script }}.sh
    - user: root
    - group: nagios
    - mode: '0750'
    - require:
      - file: /etc/icinga2/scripts
      - file: /etc/icinga2/scripts/webhook_config.sh
{%- endfor %}

# ── Icingaweb2 configuration ───────────────────────────────────────────────────

/etc/icingaweb2:
  file.directory:
    - user: www-data
    - group: icingaweb2
    - mode: '2770'
    - require:
      - pkg: monitoring_packages

/etc/icingaweb2/modules/director:
  file.directory:
    - user: www-data
    - group: icingaweb2
    - mode: '2770'
    - makedirs: True
    - require:
      - file: /etc/icingaweb2

{%- for conf, src in [
    ('config.ini',         'config.ini.jinja'),
    ('resources.ini',      'resources.ini.jinja'),
    ('authentication.ini', 'authentication.ini.jinja'),
    ('roles.ini',          'roles.ini.jinja'),
] %}
/etc/icingaweb2/{{ conf }}:
  file.managed:
    - source: salt://monitoring/files/icingaweb2/{{ src }}
    - template: jinja
    - user: www-data
    - group: icingaweb2
    - mode: '0660'
    - require:
      - file: /etc/icingaweb2
{%- endfor %}

/etc/icingaweb2/modules/director/config.ini:
  file.managed:
    - source: salt://monitoring/files/icingaweb2/modules/director/config.ini.jinja
    - template: jinja
    - user: www-data
    - group: icingaweb2
    - mode: '0660'
    - require:
      - file: /etc/icingaweb2/modules/director

icingaweb2_enable_director:
  cmd.run:
    - name: icingacli module enable director
    - unless: icingacli module list | grep -q '^director.*enabled'
    - runas: www-data
    - require:
      - file: /etc/icingaweb2/modules/director/config.ini

# ── Director DB schema + kickstart ────────────────────────────────────────────

director_migration:
  cmd.run:
    - name: >-
        icingacli director migration run --verbose &&
        touch /etc/icinga2/.director_migration_done
    - creates: /etc/icinga2/.director_migration_done
    - runas: www-data
    - require:
      - cmd: icingaweb2_enable_director
      - cmd: monitoring_db_director
      - service: icinga2

director_kickstart:
  cmd.run:
    - name: >-
        icingacli director kickstart run &&
        touch /etc/icinga2/.director_kickstart_done
    - creates: /etc/icinga2/.director_kickstart_done
    - runas: www-data
    - require:
      - cmd: director_migration

# ── Nginx ──────────────────────────────────────────────────────────────────────

/etc/nginx/sites-available/icingaweb2.conf:
  file.managed:
    - source: salt://monitoring/files/nginx/icingaweb2.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: monitoring_packages

/etc/nginx/sites-enabled/icingaweb2.conf:
  file.symlink:
    - target: /etc/nginx/sites-available/icingaweb2.conf
    - require:
      - file: /etc/nginx/sites-available/icingaweb2.conf

/etc/nginx/sites-enabled/default:
  file.absent:
    - require:
      - file: /etc/nginx/sites-enabled/icingaweb2.conf

nginx:
  service.running:
    - enable: True
    - watch:
      - file: /etc/nginx/sites-available/icingaweb2.conf
    - require:
      - pkg: monitoring_packages

php_fpm:
  service.running:
    - name: php-fpm
    - enable: True
    - require:
      - pkg: monitoring_packages
