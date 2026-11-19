{%- set codename = grains['oscodename'] %}

php_repo_prereqs:
  pkg.installed:
    - pkgs:
      - ca-certificates
      - curl
      - gnupg

php_sury_apt_key:
  cmd.run:
    - name: curl -fsSL https://packages.sury.org/php/apt.gpg -o /usr/share/keyrings/deb.sury.org-php.gpg
    - creates: /usr/share/keyrings/deb.sury.org-php.gpg
    - require:
      - pkg: php_repo_prereqs

/etc/apt/sources.list.d/php-sury.list:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - contents: |
        deb [signed-by=/usr/share/keyrings/deb.sury.org-php.gpg] https://packages.sury.org/php/ {{ codename }} main
    - require:
      - cmd: php_sury_apt_key

php_sury_apt_update:
  cmd.run:
    - name: apt-get update -qq
    - onchanges:
      - file: /etc/apt/sources.list.d/php-sury.list
