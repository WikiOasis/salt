# Custom WikiOasis MOTD: ANSI logo + welcome banner + live system stats.
#
# Rendered for interactive logins from /etc/profile.d, NOT /etc/update-motd.d:
# on Debian, pam_motd does not execute update-motd.d scripts (that run-parts
# behaviour is an Ubuntu-only patch), so a script dropped there never runs.
# Login shells source /etc/profile.d/*.sh on both Debian and Ubuntu, so that is
# where we hook in. sshd sets `PrintMotd no` + `UsePAM yes` (metal.ssh), and we
# blank /etc/motd below, so the profile.d banner is the only MOTD shown.

motd_logo:
  file.managed:
    - name: /etc/wikioasis/logo.ansi
    - source: salt://motd/files/logo.ansi
    - makedirs: True
    - user: root
    - group: root
    - mode: '0644'

/usr/local/sbin/wikioasis-motd:
  file.managed:
    - source: salt://motd/files/wikioasis-motd
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: motd_logo

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
