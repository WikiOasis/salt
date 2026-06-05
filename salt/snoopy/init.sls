# snoopy logs every (TTY) command execution to journald via /dev/log; those
# entries are picked up by monitoring.otelcol and shipped to Sentry, where they
# carry syslog_identifier=snoopy and the audit=command tag.

snoopy_pkg:
  pkg.installed:
    - name: snoopy

/etc/snoopy.ini:
  file.managed:
    - source: salt://snoopy/files/snoopy.ini
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: snoopy_pkg

# The Debian package normally wires libsnoopy.so into /etc/ld.so.preload on
# install; this is an idempotent fallback in case it didn't.
snoopy_ld_preload:
  cmd.run:
    - name: |
        lib=$(ls /usr/lib/*/libsnoopy.so 2>/dev/null | head -n1)
        if [ -n "$lib" ]; then echo "$lib" >> /etc/ld.so.preload; fi
    - unless: grep -q libsnoopy /etc/ld.so.preload
    - require:
      - pkg: snoopy_pkg
