# Adapted from https://gitlab.com/telepedia/saltstack/-/blob/main/salt/users/init.sls

# Revoke any users with a role of revoked
{%- for user, args in pillar.get('revokedusers', {}).items() %}
{{ user }}:
  user.absent:
    - purge: True
    - force: True
  group.absent: []

{%- if args['ssh-keys'] %}
{{ user }}_root_key:
  ssh_auth.absent:
    - user: root
    - names:
      {%- for key in args['ssh-keys'] %}
      - {{ key }}
      {%- endfor %}
{%- endif %}

{{ user }}_sudoers_cleanup:
  cmd.run:
    - name: find /etc/sudoers.d -name '{{ user }}_*' -delete
    - onlyif: find /etc/sudoers.d -name '{{ user }}_*' | grep -q .
{%- endfor %}

# Add users and assign groups
{%- set server_groups = pillar.get('server_groups', ['ops']) %}
{%- set server_users = [] %}
{%- for group in server_groups %}
  {%- set group_members = pillar.get('groups', {}).get(group, {}).get('members', []) %}
  {%- do server_users.extend(group_members) %}
{%- endfor %}
{%- set server_users = server_users|unique %}

{%- for user, args in pillar.get('users', {}).items() if user in server_users %}
{{ user }}:
  group.present:
    - gid: {{ args['gid'] }}
  user.present:
    - fullname: {{ args['fullname'] }}
    - uid: {{ args['uid'] }}
    - gid: {{ args['gid'] }}
    - shell: /bin/bash
    - allow_gid_change: True
    - allow_uid_change: True
    - onlyif: |
        if ! id {{ user }} > /dev/null 2>&1; then
          exit 0
        fi

        if pgrep -u {{ user }} > /dev/null 2>&1; then
          exit 1
        fi

        current_groups=$(groups {{ user }} 2>/dev/null | cut -d: -f2 | sed 's/^ *//' | tr ' ' '\n' | sort | tr '\n' ' ')
        {%- if grains['os'] == 'Ubuntu' %}
        expected_groups="{{ user }} adm cdrom dip plugdev sudo"
        {%- else %}
        expected_groups="{{ user }}"
        {%- endif %}
        expected_sorted=$(echo $expected_groups | tr ' ' '\n' | sort | tr '\n' ' ')

        [ "$current_groups" != "$expected_sorted" ]
    {%- if grains['os'] == 'Ubuntu' %}
    - groups:
      - sudo
      - adm
      - dip
      - cdrom
      - plugdev
    {%- endif %}

{%- if args['ssh-keys'] %}
{{ user }}_root_key:
  ssh_auth.present:
    - user: root
    - names:
      {%- for key in args['ssh-keys'] %}
      - {{ key }}
      {%- endfor %}

{{ user }}_key:
  ssh_auth.present:
    - user: {{ user }}
    - names:
      {%- for key in args['ssh-keys'] %}
      - {{ key }}
      {%- endfor %}
{%- endif %}
{%- endfor %}

# Add groups and manage memberships and privileges
{%- for group, args in pillar.get('groups', {}).items() %}
{%- if group in pillar.get('server_groups', []) %}
{{ group }}:
  group.present:
    - gid: {{ args['gid'] }}
    {%- if args['members'] %}
    - members:
      {%- for member in args['members'] %}
      - {{ member }}
      {%- endfor %}
    {%- endif %}

{%- for member in args['members'] %}
/etc/sudoers.d/{{ member }}_{{ group }}:
  file.managed:
    - contents:
      {%- for priv in args['privileges'] %}
      - "{{ member }} {{ priv }}"
      {%- endfor %}
    - user: root
    - group: root
    - mode: '0440'
{%- endfor %}
{%- endif %}
{%- endfor %}

# Allow sudoers to sudo without passwords.
# This is to avoid having to manage passwords in addition to keys
/etc/sudoers.d/sudonopasswd:
  file.managed:
    - source: salt://users/files/sudoers.d/sudonopasswd
    - user: root
    - group: root
    - mode: '0440'
