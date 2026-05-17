{%- set hosts = salt['pillar.get']('dns_hosts', {}) %}

# All cmd.run states use `unless` to check existence first — fully idempotent.
# Run director.sls independently with: salt 'monitoring*' state.apply monitoring.director

# ── Host template ──────────────────────────────────────────────────────────────

director_template_generic_salt_host:
  cmd.run:
    - name: >-
        icingacli director host create --json
        '{"object_name":"generic-salt-host","object_type":"template",
          "check_command":"hostalive","max_check_attempts":3,
          "check_interval":60,"retry_interval":30,
          "enable_notifications":true,"enable_active_checks":true}'
    - unless: icingacli director host show --name "generic-salt-host" >/dev/null 2>&1
    - runas: www-data

# ── Notification commands ──────────────────────────────────────────────────────

director_cmd_discord_host:
  cmd.run:
    - name: >-
        icingacli director command create --json
        '{"object_name":"notify-host-by-discord","object_type":"object",
          "command":"/etc/icinga2/scripts/discord_host_notification.sh",
          "methods_execute":"PluginNotification","timeout":30,
          "env":{
            "NOTIFICATIONTYPE":"$notification.type$",
            "HOSTNAME":"$host.name$",
            "HOSTSTATE":"$host.state$",
            "HOSTOUTPUT":"$host.output$",
            "LONGDATETIME":"$icinga.long_date_time$"
 }}'
    - unless: icingacli director command show --name "notify-host-by-discord" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_template_generic_salt_host

director_cmd_discord_service:
  cmd.run:
    - name: >-
        icingacli director command create --json
        '{"object_name":"notify-service-by-discord","object_type":"object",
          "command":"/etc/icinga2/scripts/discord_service_notification.sh",
          "methods_execute":"PluginNotification","timeout":30,
          "env":{
            "NOTIFICATIONTYPE":"$notification.type$",
            "HOSTNAME":"$host.name$",
            "SERVICENAME":"$service.name$",
            "SERVICESTATE":"$service.state$",
            "SERVICEOUTPUT":"$service.output$",
            "LONGDATETIME":"$icinga.long_date_time$"
 }}'
    - unless: icingacli director command show --name "notify-service-by-discord" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_cmd_discord_host

director_cmd_slack_host:
  cmd.run:
    - name: >-
        icingacli director command create --json
        '{"object_name":"notify-host-by-slack","object_type":"object",
          "command":"/etc/icinga2/scripts/slack_host_notification.sh",
          "methods_execute":"PluginNotification","timeout":30,
          "env":{
            "NOTIFICATIONTYPE":"$notification.type$",
            "HOSTNAME":"$host.name$",
            "HOSTSTATE":"$host.state$",
            "HOSTOUTPUT":"$host.output$",
            "LONGDATETIME":"$icinga.long_date_time$"
 }}'
    - unless: icingacli director command show --name "notify-host-by-slack" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_cmd_discord_service

director_cmd_slack_service:
  cmd.run:
    - name: >-
        icingacli director command create --json
        '{"object_name":"notify-service-by-slack","object_type":"object",
          "command":"/etc/icinga2/scripts/slack_service_notification.sh",
          "methods_execute":"PluginNotification","timeout":30,
          "env":{
            "NOTIFICATIONTYPE":"$notification.type$",
            "HOSTNAME":"$host.name$",
            "SERVICENAME":"$service.name$",
            "SERVICESTATE":"$service.state$",
            "SERVICEOUTPUT":"$service.output$",
            "LONGDATETIME":"$icinga.long_date_time$"
 }}'
    - unless: icingacli director command show --name "notify-service-by-slack" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_cmd_slack_host

# ── Notification user (placeholder required by Icinga2) ───────────────────────

director_user_webhook:
  cmd.run:
    - name: >-
        icingacli director user create --json
        '{"object_name":"webhook-notify","object_type":"object",
          "enable_notifications":true}'
    - unless: icingacli director user show --name "webhook-notify" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_cmd_slack_service

# ── Per-host objects ───────────────────────────────────────────────────────────
# Role is inferred from the hostname prefix:
#   proxy*      → hostalive + ssh + http + NRPE
#   db*         → hostalive + ssh + tcp/3306 + NRPE (incl. disk_srv)
#   monitoring* → hostalive + ssh + http + NRPE
#   bastion*    → hostalive + ssh + NRPE
#   salt*       → hostalive + ssh + NRPE
#
# NRPE checks on every host: load, disk_root, procs, swap, mem
# NRPE service notifications: Discord + Slack per-check

{%- for hostname, host_data in hosts.items() %}
{%- set sid = hostname | replace('-', '_') | replace('.', '_') %}
{%- set is_proxy      = hostname.startswith('proxy') %}
{%- set is_db         = hostname.startswith('db') %}
{%- set is_monitoring = hostname.startswith('monitoring') %}

# -- {{ hostname }} ({{ host_data.ip }}) ---------------------------------------

director_host_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director host create --json
        '{"object_name":"{{ hostname }}","object_type":"object",
          "address":"{{ host_data.ip }}","imports":["generic-salt-host"],
          "vars":{"os":"Linux" }}'
    - unless: icingacli director host show --name "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_user_webhook

# connectivity checks ──────────────────────────────────────────────────────────

director_svc_ssh_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"ssh","object_type":"object",
          "check_command":"ssh","host_id":"{{ hostname }}",
          "check_interval":300,"retry_interval":60}'
    - unless: icingacli director service show --name "ssh" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

{%- if is_proxy or is_monitoring %}
director_svc_http_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"http","object_type":"object",
          "check_command":"http","host_id":"{{ hostname }}",
          "vars":{"http_uri":"/"},"check_interval":300,"retry_interval":60}'
    - unless: icingacli director service show --name "http" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}
{%- endif %}

{%- if is_db %}
director_svc_mysql_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"mysql_port","object_type":"object",
          "check_command":"tcp","host_id":"{{ hostname }}",
          "vars":{"tcp_port":3306},"check_interval":300,"retry_interval":60}'
    - unless: icingacli director service show --name "mysql_port" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}
{%- endif %}

# NRPE resource checks ─────────────────────────────────────────────────────────

director_svc_load_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"load","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":60,"retry_interval":30,
          "vars":{"nrpe_command":"check_load","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "load" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

director_svc_disk_root_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"disk_root","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":300,"retry_interval":60,
          "vars":{"nrpe_command":"check_disk_root","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "disk_root" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

director_svc_procs_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"procs","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":300,"retry_interval":60,
          "vars":{"nrpe_command":"check_procs","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "procs" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

director_svc_swap_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"swap","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":300,"retry_interval":60,
          "vars":{"nrpe_command":"check_swap","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "swap" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

director_svc_mem_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"mem","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":60,"retry_interval":30,
          "vars":{"nrpe_command":"check_mem","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "mem" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}

{%- if is_db %}
director_svc_disk_srv_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director service create --json
        '{"object_name":"disk_srv","object_type":"object",
          "check_command":"nrpe","host_id":"{{ hostname }}",
          "check_interval":300,"retry_interval":60,
          "vars":{"nrpe_command":"check_disk_srv","nrpe_no_ssl":true }}'
    - unless: icingacli director service show --name "disk_srv" --host "{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}
{%- endif %}

# NRPE service notifications (Discord + Slack per check) ───────────────────────

{%- for svc in (['load', 'disk_root', 'procs', 'swap', 'mem'] + (['disk_srv'] if is_db else [])) %}
director_notif_discord_svc_{{ sid }}_{{ svc }}:
  cmd.run:
    - name: >-
        icingacli director notification create --json
        '{"object_name":"discord-svc-{{ hostname }}-{{ svc }}","object_type":"object",
          "host_id":"{{ hostname }}","service_id":"{{ svc }}",
          "command_id":"notify-service-by-discord","users":["webhook-notify"],
          "states":["OK","Warning","Critical","Unknown"],
          "types":["Problem","Recovery","Acknowledgement","FlappingStart","FlappingEnd"]}'
    - unless: icingacli director notification show --name "discord-svc-{{ hostname }}-{{ svc }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_svc_{{ svc }}_{{ sid }}
      - cmd: director_cmd_discord_service
      - cmd: director_user_webhook

director_notif_slack_svc_{{ sid }}_{{ svc }}:
  cmd.run:
    - name: >-
        icingacli director notification create --json
        '{"object_name":"slack-svc-{{ hostname }}-{{ svc }}","object_type":"object",
          "host_id":"{{ hostname }}","service_id":"{{ svc }}",
          "command_id":"notify-service-by-slack","users":["webhook-notify"],
          "states":["OK","Warning","Critical","Unknown"],
          "types":["Problem","Recovery","Acknowledgement","FlappingStart","FlappingEnd"]}'
    - unless: icingacli director notification show --name "slack-svc-{{ hostname }}-{{ svc }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_svc_{{ svc }}_{{ sid }}
      - cmd: director_cmd_slack_service
      - cmd: director_user_webhook
{%- endfor %}

# host-level notifications (hostalive up/down) ─────────────────────────────────

director_notif_discord_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director notification create --json
        '{"object_name":"discord-host-{{ hostname }}","object_type":"object",
          "host_id":"{{ hostname }}","command_id":"notify-host-by-discord",
          "users":["webhook-notify"],
          "states":["Up","Down"],
          "types":["Problem","Recovery","Acknowledgement","FlappingStart","FlappingEnd"]}'
    - unless: icingacli director notification show --name "discord-host-{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}
      - cmd: director_cmd_discord_host
      - cmd: director_user_webhook

director_notif_slack_{{ sid }}:
  cmd.run:
    - name: >-
        icingacli director notification create --json
        '{"object_name":"slack-host-{{ hostname }}","object_type":"object",
          "host_id":"{{ hostname }}","command_id":"notify-host-by-slack",
          "users":["webhook-notify"],
          "states":["Up","Down"],
          "types":["Problem","Recovery","Acknowledgement","FlappingStart","FlappingEnd"]}'
    - unless: icingacli director notification show --name "slack-host-{{ hostname }}" >/dev/null 2>&1
    - runas: www-data
    - require:
      - cmd: director_host_{{ sid }}
      - cmd: director_cmd_slack_host
      - cmd: director_user_webhook

{%- endfor %}

# ── Deploy pending config ──────────────────────────────────────────────────────
# Runs after all objects are created; --wait blocks until Icinga2 has reloaded.

director_deploy:
  cmd.run:
    - name: icingacli director config deploy --wait
    - runas: www-data
    - require:
      - cmd: director_user_webhook
{%- for hostname in hosts.keys() %}
{%- set sid = hostname | replace('-', '_') | replace('.', '_') %}
      - cmd: director_host_{{ sid }}
      - cmd: director_svc_ssh_{{ sid }}
      - cmd: director_svc_load_{{ sid }}
      - cmd: director_svc_mem_{{ sid }}
      - cmd: director_notif_discord_{{ sid }}
      - cmd: director_notif_slack_{{ sid }}
{%- endfor %}
