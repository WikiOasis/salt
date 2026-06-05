# Custom WikiOasis MOTD: ANSI logo + welcome banner + live system stats,
# rendered at login by Debian's pam_motd (see /etc/update-motd.d). sshd sets
# `PrintMotd no` and `UsePAM yes` (metal.ssh), so PAM is the only thing that
# prints the MOTD and there is no double output.

motd_logo:
  file.managed:
    - name: /etc/wikioasis/logo.ansi
    - source: salt://motd/files/logo.ansi
    - makedirs: True
    - user: root
    - group: root
    - mode: '0644'

/etc/update-motd.d/10-wikioasis:
  file.managed:
    - source: salt://motd/files/10-wikioasis
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - file: motd_logo

# Drop the stock Debian script so our banner is the entire MOTD.
/etc/update-motd.d/10-uname:
  file.absent: []

# Blank the static motd; the dynamic one above replaces it.
/etc/motd:
  file.managed:
    - contents: ''
    - user: root
    - group: root
    - mode: '0644'
