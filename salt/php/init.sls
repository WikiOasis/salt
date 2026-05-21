{%- set cfg = salt['pillar.get']('php', {}) %}
{%- set version = cfg.get('version', '8.3') %}
{%- set extensions = cfg.get('extensions', ['fpm', 'mysql', 'xml', 'mbstring', 'intl', 'curl', 'gd', 'zip', 'apcu', 'igbinary']) %}
{%- set extra_packages = cfg.get('extra_packages', ['php-excimer']) %}
{%- set fpm = cfg.get('fpm', {}) %}
{%- set pool = fpm.get('pool', 'www') %}

install_php:
  pkg.installed:
    - pkgs:
      - php{{ version }}
{%- for ext in extensions %}
      - php{{ version }}-{{ ext }}
{%- endfor %}
{%- for pkg in extra_packages %}
      - {{ pkg }}
{%- endfor %}

/etc/php/{{ version }}/fpm/pool.d/{{ pool }}.conf:
  file.managed:
    - source: salt://php/files/www.conf.jinja
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
