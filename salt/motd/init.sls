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
# Several logo variants ship: the standard blue mark, a pride-month rainbow
# mark, and the WikiOasis-WikiSpark and WikiSpark co-brand marks.
# `motd:theme` in pillar selects which one /etc/wikioasis/logo.ansi points at
# (default: blue); set it to one of blue|pride|wikioasis-wikispark|wikispark
# and re-highstate to swap, fleet-wide.

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

motd_logo_wikioasis_wikispark:
  file.managed:
    - name: /etc/wikioasis/logo-wikioasis-wikispark.ansi
    - source: salt://motd/files/logo-wikioasis-wikispark.ansi
    - user: root
    - group: root
    - mode: '0644'

motd_logo_wikispark:
  file.managed:
    - name: /etc/wikioasis/logo-wikispark.ansi
    - source: salt://motd/files/logo-wikispark.ansi
    - user: root
    - group: root
    - mode: '0644'

# Active variant — swap by setting pillar motd:theme to
# blue|pride|wikioasis-wikispark|wikispark.
# force: replace the plain file left by the earlier file.managed version.
/etc/wikioasis/logo.ansi:
  file.symlink:
    - target: /etc/wikioasis/logo-{{ theme }}.ansi
    - force: True
    - require:
      - file: motd_logo_blue
      - file: motd_logo_pride
      - file: motd_logo_wikioasis_wikispark
      - file: motd_logo_wikispark

# Random prod joke pool — one joke per line, sourced from pillar motd:jokes.
# The banner script picks a random line at login; edit the list in pillar.
/etc/wikioasis/motd-jokes:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - contents:
      {%- for joke in salt['pillar.get']('motd:jokes', []) %}
      - {{ joke | yaml_encode }}
      {%- endfor %}

/usr/local/sbin/wikioasis-motd:
  file.managed:
    - source: salt://motd/files/wikioasis-motd
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: /etc/wikioasis/logo.ansi
      - file: /etc/wikioasis/motd-jokes

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
