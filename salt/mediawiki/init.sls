# Staging server — mwdeploy script, config, deploy user, and SSH key
{%- set mw = salt['pillar.get']('mediawiki', {}) %}
{%- set deploy_user = mw.get('deploy_user', 'mwdeploy') %}
{%- set staging_path = mw.get('staging_path', '/srv/mediawiki-staging') %}
{%- set prod_path = mw.get('prod_path', '/srv/mediawiki') %}

# Deploy user
{{ deploy_user }}:
  user.present:
    - system: true
    - shell: /bin/bash
    - home: /home/{{ deploy_user }}
    - createhome: true
  group.present: []

/home/{{ deploy_user }}/.ssh:
  file.directory:
    - user: {{ deploy_user }}
    - group: {{ deploy_user }}
    - mode: '0700'
    - require:
      - user: {{ deploy_user }}

# Authorize the deploy user's own key (populated after first keygen run)
{%- if mw.get('deploy_ssh_public_key') %}
{{ deploy_user }}_ssh_auth:
  ssh_auth.present:
    - user: {{ deploy_user }}
    - names:
      - {{ mw['deploy_ssh_public_key'] }}
    - require:
      - file: /home/{{ deploy_user }}/.ssh
{%- endif %}

# The script
/usr/local/bin/mwdeploy:
  file.managed:
    - source: salt://mediawiki/files/mwdeploy
    - user: root
    - group: root
    - mode: '0755'

# Config directory + rendered config
/etc/mwdeploy:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/etc/mwdeploy/config.yaml:
  file.managed:
    - source: salt://mediawiki/files/config.yaml.jinja
    - template: jinja
    - user: root
    - group: {{ deploy_user }}
    - mode: '0640'
    - require:
      - file: /etc/mwdeploy

# Log file (pre-create so the deploy user can write to it)
/var/log/mwdeploy.log:
  file.managed:
    - user: {{ deploy_user }}
    - group: {{ deploy_user }}
    - mode: '0640'
    - replace: false

# Staging directory owned by www-data (git operations run as www-data)
{{ staging_path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: true

# Production directory on the staging/canary host
{{ prod_path }}:
  file.directory:
    - user: www-data
    - group: www-data
    - mode: '0755'
    - makedirs: true

# Allow the deploy user to git pull as www-data, rsync as root, patch and l10n rebuild
/etc/sudoers.d/mwdeploy_staging:
  file.managed:
    - contents:
      - "{{ deploy_user }} ALL=(www-data) NOPASSWD: /usr/bin/git"
      - "{{ deploy_user }} ALL=(root) NOPASSWD: /usr/bin/rsync"
      - "{{ deploy_user }} ALL=(www-data) NOPASSWD: /usr/bin/patch"
      - "{{ deploy_user }} ALL=(www-data) NOPASSWD: {{ prod_path }}/scripts/mwscript.php"
    - user: root
    - group: root
    - mode: '0440'

# python3-yaml is required by the mwdeploy script
python3-yaml:
  pkg.installed: []
