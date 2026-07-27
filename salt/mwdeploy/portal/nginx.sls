# nginx + a dedicated php-fpm pool fronting the deploy portal on the Salt
# master. The master runs no other web service, so this is a standalone vhost
# rather than reusing salt/nginx (which is tuned for the apps*/mw* fleet).

{%- set p = salt['pillar.get']('mwdeploy_portal', {}) %}
{%- set php_version = p.get('php_version', '8.4') %}

nginx:
  pkg.installed: []

/etc/nginx/sites-enabled/default:
  file.absent:
    - require:
      - pkg: nginx

/etc/php/{{ php_version }}/fpm/pool.d/deploy-portal.conf:
  file.managed:
    - source: salt://mwdeploy/portal/files/php-fpm-pool.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'

/etc/nginx/conf.d/deploy-portal.conf:
  file.managed:
    - source: salt://mwdeploy/portal/files/nginx-deploy-portal.conf.jinja
    - template: jinja
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - pkg: nginx

php-fpm-deploy-portal:
  service.running:
    - name: php{{ php_version }}-fpm
    - enable: True
    - watch:
      - file: /etc/php/{{ php_version }}/fpm/pool.d/deploy-portal.conf

nginx_deploy_portal_service:
  service.running:
    - name: nginx
    - enable: True
    - reload: True
    - watch:
      - file: /etc/nginx/conf.d/deploy-portal.conf
    - require:
      - pkg: nginx
      - file: /etc/nginx/sites-enabled/default
