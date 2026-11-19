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
      - {{ ('php' ~ version ~ '-' ~ pkg[4:]) if pkg.startswith('php-') else pkg }}
{% endfor %}

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
