{%- set apt_mirror = salt['pillar.get']('apt:mirror', 'deb.debian.org') %}
{%- set codename = grains['oscodename'] %}

set_timezone:
  timezone.system:
    - name: {{ salt['pillar.get']('timezone', 'Etc/UTC') }}

/etc/apt/sources.list:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - contents: |
        deb http://{{ apt_mirror }}/debian {{ codename }} main contrib non-free non-free-firmware
        deb http://{{ apt_mirror }}/debian {{ codename }}-updates main contrib non-free non-free-firmware
        deb http://security.debian.org/debian-security {{ codename }}-security main contrib non-free non-free-firmware

apt_update:
  cmd.run:
    - name: apt-get update -qq
    - onchanges:
      - file: /etc/apt/sources.list
