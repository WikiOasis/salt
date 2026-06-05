# Custom WikiOasis MOTD: ANSI logo (left) + welcome banner & live system stats
# (right), shown for interactive logins.
#
# Rendered from /etc/profile.d, NOT /etc/update-motd.d: on Debian, pam_motd does
# not execute update-motd.d scripts (that run-parts behaviour is an Ubuntu-only
# patch), so a script dropped there never runs. Login shells source
# /etc/profile.d/*.sh on both Debian and Ubuntu, so that is where we hook in.
# sshd sets `PrintMotd no` + `UsePAM yes` (metal.ssh) and we blank /etc/motd, so
# the profile.d banner is the only MOTD shown.
#
# Two logo variants ship: the standard blue mark and a pride-month rainbow mark.
# `motd:theme` in pillar selects which one /etc/wikioasis/logo.ansi points at
# (default: blue); flip it to `pride` and re-highstate to swap, fleet-wide.

{%- set theme = salt['pillar.get']('motd:theme', 'blue') %}

motd_logo_blue:
  file.managed:
    - name: /etc/wikioasis/logo-blue.ansi
    - source: salt://motd/files/logo-blue.ansi
    - makedirs: True
    - user: root
    - group: root
    - mode: '0644'

motd_logo_pride:
  file.managed:
    - name: /etc/wikioasis/logo-pride.ansi
    - source: salt://motd/files/logo-pride.ansi
    - user: root
    - group: root
    - mode: '0644'

# Active variant — swap by setting pillar motd:theme to blue|pride.
# force: replace the plain file left by the earlier file.managed version.
/etc/wikioasis/logo.ansi:
  file.symlink:
    - target: /etc/wikioasis/logo-{{ theme }}.ansi
    - force: True
    - require:
      - file: motd_logo_blue
      - file: motd_logo_pride

/usr/local/sbin/wikioasis-motd:
  file.managed:
    - source: salt://motd/files/wikioasis-motd
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: /etc/wikioasis/logo.ansi

/etc/profile.d/zz-wikioasis-motd.sh:
  file.managed:
    - source: salt://motd/files/zz-wikioasis-motd.sh
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: /usr/local/sbin/wikioasis-motd

# Clean up the earlier update-motd.d approach, which never ran on Debian.
/etc/update-motd.d/10-wikioasis:
  file.absent: []

# Blank the static motd so only our banner shows.
/etc/motd:
  file.managed:
    - contents: ''
    - user: root
    - group: root
    - mode: '0644'
