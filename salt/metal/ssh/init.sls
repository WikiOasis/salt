sshd_config:
   file.managed:
      - name: /etc/ssh/sshd_config
      - source: salt://metal/ssh/files/sshd_config.jinja
      - template: jinja
      - user: root
      - group: root
      - mode: '0600'
