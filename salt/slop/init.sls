{%- set s = salt['pillar.get']('slop', {}) %}
{%- set user = s.get('user', 'mwdeploy') %}
{%- set path = s.get('path', '/opt/slop') %}
{%- set php = s.get('php_version', '8.4') %}
{%- set live = s.get('live_path', '/srv/mediawiki') %}

slop-packages:
  pkg.installed:
    - pkgs:
      - git
      - rsync
      - curl
      - python3
      - python3-yaml

slop-code:
  git.latest:
    - name: {{ s.get('repo', 'https://github.com/WikiOasis/slop.git') }}
    - target: {{ path }}
    - rev: {{ s.get('rev', 'main') }}
    - branch: {{ s.get('rev', 'main') }}
    - user: root
    - force_reset: True
    - submodules: False
    - require:
      - pkg: slop-packages

/usr/local/lib/slop:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'

/usr/local/lib/slop/run:
  file.managed:
    - source: salt://slop/files/run.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: /usr/local/lib/slop

/usr/local/bin/slop:
  file.managed:
    - source: salt://slop/files/slop.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - git: slop-code

slop-verify:
  cmd.run:
    - name: /usr/local/bin/slop --version
    - runas: {{ user }}
    - require:
      - user: {{ user }}
    - onchanges:
      - git: slop-code
      - file: /usr/local/bin/slop

/etc/sudoers.d/slop:
  file.managed:
    - user: root
    - group: root
    - mode: '0440'
    - check_cmd: /usr/sbin/visudo -c -f
    - contents: |
        Defaults!/usr/local/lib/slop/run env_keep += "SLOP_INVOKER SLOP_FORWARDED"
        %ops ALL=({{ user }}) NOPASSWD: /usr/local/lib/slop/run, /usr/local/lib/slop/run *
        %mediawiki-admins ALL=({{ user }}) NOPASSWD: /usr/local/lib/slop/run, /usr/local/lib/slop/run *
        {{ user }} ALL=(root) NOPASSWD: /usr/bin/rsync
        {{ user }} ALL=(root) NOPASSWD: /usr/bin/systemctl reload php{{ php }}-fpm, /usr/bin/systemctl restart php{{ php }}-fpm, /usr/bin/systemctl reload nginx
        {%- for unit in s.get('units', []) %}
        {{ user }} ALL=(root) NOPASSWD: /usr/bin/systemctl restart {{ unit }}
        {%- endfor %}
        {{ user }} ALL=(www-data) NOPASSWD: /usr/bin/php {{ live }}/scripts/mwscript.php *
        {%- for command in s.get('www_data_commands', []) %}
        {{ user }} ALL=(www-data) NOPASSWD: {{ command }}
        {%- endfor %}
