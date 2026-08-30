# Non-secret configuration for TSPortal (https://github.com/WikiOasis/TSPortal),
# the Trust & Safety queue. Runs on apps-us-east-021 behind the `apps` haproxy
# backend; the vhost is salt/nginx/files/safety.conf.jinja.
#
# Secrets (db_password, app_key, oauth_client_secret, s2s_secret, the R2 keys
# and the Slack webhooks) live in pillar/private/init.sls — see
# pillar/private/init.sls.example for the shape.
#
# PHP is deliberately not configured here: TSPortal shares the apps* php-fpm
# pool (pillar/php + pillar/php/apps.sls) with Phorge and WOPortal, so the
# version and socket are read from the `php` pillar rather than duplicated.

tsportal:
  domain: safety.wikioasis.org
  path: /srv/tsportal
  repo: https://github.com/WikiOasis/TSPortal.git
  rev: main

  db:
    name: tsportal
    user: tsportal_new
    host: db-other-us-east-011.ovvin.wonet

  mediawiki:
    central_url: https://meta.wikioasis.org
    api_url: https://meta.wikioasis.org/w/api.php
    rest_url: https://meta.wikioasis.org/w/rest.php
    user_agent: "TSPortal/1.0 (https://safety.wikioasis.org; trustandsafety@wikioasis.org)"
    oauth:
      scopes: basic
      redirect_uri: https://safety.wikioasis.org/auth/mediawiki/callback
    bootstrap_admins: "Zippy"
    supported_actions: lock,unlock,warn,note,block,unblock,delete-wiki,undelete-wiki,rename,renamestatus,removepii
    centralauth_lock: true
    push_enabled: true
    pii:
      enabled: true
      username_prefix: WikiOasisGDPR
      rename_timeout_hours: 24

  attachments:
    enabled: true
    disk: s3
    prefix: tsportal
    max_bytes: 26214400
    max_per_case: 20
    r2:
      bucket: wikioasis-media
      endpoint: https://a772d1f94009a9592b7de7cfd35218de.r2.cloudflarestorage.com
      region: auto
      path_style: true
      public_url: https://cdn.wikioasis.org

  threat_to_life:
    categories: threats,self-harm,threat-to-life,threat-of-physical-harm
    priority: urgent

  slack:
    enabled: true
    mention: "<!channel>"
    include_subjects: false
    ignore: auth.login,auth.logout,attachment.read,wikis.synced

  mail:
    mailer: smtp
    host: smtp.gmail.com
    port: 465
    scheme: smtps
    ehlo_domain: safety.wikioasis.org
    from_address: safety@wikioasis.org
    from_name: WikiOasis Trust & Safety
  log_level: info
