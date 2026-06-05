nginx:
  pkg.installed: []

logrotate_pkg:
  pkg.installed:
    - name: logrotate

# Logs ship to Sentry (see monitoring.otelcol), so keep little on disk. The
# access.log postrotate seed preserves the last 500 lines for check_nginx_errors.
/etc/logrotate.d/nginx:
  file.managed:
    - source: salt://nginx/files/logrotate-nginx
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx
      - pkg: logrotate_pkg

/etc/nginx/snippets:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - pkg: nginx

/etc/nginx/snippets/mediawiki-common.conf:
  file.managed:
    - source: salt://nginx/files/mediawiki-common.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: /etc/nginx/snippets

/etc/nginx/conf.d/mediawiki-vhosts.conf:
  file.managed:
    - source: salt://nginx/files/mediawiki-vhosts.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx
      - file: /etc/nginx/snippets/mediawiki-common.conf

/etc/nginx/conf.d/custom_domains:
  file.absent: []

/etc/nginx/conf.d/custom_domains_include.conf:
  file.absent: []

/etc/nginx/conf.d/custom_domains.conf:
  file.managed:
    - source: salt://nginx/files/custom-domains.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx
      - file: /etc/nginx/snippets/mediawiki-common.conf

/etc/nginx/conf.d/phorge.conf:
  file.managed:
    - source: salt://nginx/files/phorge.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx

/etc/nginx/conf.d/safety.conf:
  file.managed:
    - source: salt://nginx/files/safety.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx

/etc/nginx/sites-enabled/default:
  file.absent:
    - require:
      - pkg: nginx

nginx_service:
  service.running:
    - name: nginx
    - enable: True
    - reload: True
    - watch:
      - file: /etc/nginx/snippets/mediawiki-common.conf
      - file: /etc/nginx/conf.d/mediawiki-vhosts.conf
      - file: /etc/nginx/conf.d/custom_domains.conf
      - file: /etc/nginx/conf.d/phorge.conf
      - file: /etc/nginx/conf.d/safety.conf
    - require:
      - pkg: nginx
      - file: /etc/nginx/sites-enabled/default