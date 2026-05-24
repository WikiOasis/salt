nginx:
  pkg.installed: []

/etc/nginx/snippets:
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - pkg: nginx

/etc/nginx/snippets/mediawiki-common.conf:
  file.managed:
    - source: salt://nginx/files/mediawiki-common.conf
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
  file.directory:
    - user: root
    - group: root
    - mode: '0755'
    - require:
      - pkg: nginx

# Placeholder so nginx's include glob never matches zero files
/etc/nginx/conf.d/custom_domains/_placeholder.conf:
  file.managed:
    - contents: |
        # salt managed, do not modify manually
    - user: root
    - group: root
    - mode: '0644'
    - replace: False
    - require:
      - file: /etc/nginx/conf.d/custom_domains

/etc/nginx/conf.d/custom_domains_include.conf:
  file.managed:
    - contents: |
        # salt managed, do not modify manually
        include /etc/nginx/conf.d/custom_domains/*.conf;
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: /etc/nginx/conf.d/custom_domains/_placeholder.conf

nginx_service:
  service.running:
    - name: nginx
    - enable: True
    - reload: True
    - watch:
      - file: /etc/nginx/snippets/mediawiki-common.conf
      - file: /etc/nginx/conf.d/mediawiki-vhosts.conf
    - require:
      - pkg: nginx