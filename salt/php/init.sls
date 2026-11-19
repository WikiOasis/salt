{%- set cfg = salt['pillar.get']('php', {}) %}
{%- set version = cfg.get('version', '8.4') %}
{%- set extensions = cfg.get('extensions', ['fpm', 'mysql', 'xml', 'mbstring', 'intl', 'curl', 'gd', 'zip', 'apcu', 'igbinary']) %}
{%- set extra_packages = cfg.get('extra_packages', ['php-excimer']) %}
{%- set fpm = cfg.get('fpm', {}) %}
{%- set pool = fpm.get('pool', 'www') %}

include:
  - php.repo

install_php:
  pkg.latest:
    - require:
      - cmd: php_sury_apt_update
    - pkgs:
      - php{{ version }}
{% for ext in extensions %}
      - php{{ version }}-{{ ext }}
{% endfor %}
{% for pkg in extra_packages %}
      - {{ pkg }}
{% endfor %}

{%- if version != '8.5' %}
php_remove_8_5:
  cmd.run:
    - name: apt-get purge -y 'php8.5*' && apt-get autoremove -y
    - onlyif: dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 'php8.5*' 2>/dev/null | grep -q '^.i '
    - require:
      - pkg: install_php
{%- endif %}

php_cli_alternative:
  alternatives.set:
    - name: php
    - path: /usr/bin/php{{ version }}
    - require:
      - pkg: install_php
{%- if version != '8.5' %}
      - cmd: php_remove_8_5
{%- endif %}

/etc/php/{{ version }}/fpm/pool.d/{{ pool }}.conf:
  file.managed:
    - source: salt://php/files/www.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: install_php

/etc/php/{{ version }}/fpm/php.ini:
  file.managed:
    - source: salt://php/files/php.ini.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: install_php

php{{ version }}-fpm:
  service.running:
    - enable: True
    - watch:
      - file: /etc/php/{{ version }}/fpm/pool.d/{{ pool }}.conf
      - file: /etc/php/{{ version }}/fpm/php.ini
