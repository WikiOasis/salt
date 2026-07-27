# Non-secret configuration for the mw-deploy portal (https://github.com/WikiOasis/mw-deploy).
# Secrets (db_password, app_key, reverb_app_key, reverb_app_secret) live in
# pillar/private/init.sls — see pillar/private/init.sls.example for the shape.
#
# Fleet values shared with the legacy mwdeploy CLI (staging_path, prod_path,
# canary_vhost, haproxy_backend, mw_servers, proxy_servers) are read straight
# from the existing `mediawiki` pillar rather than duplicated here.

mwdeploy_portal:
  domain: console.wikioasis.org
  path: /srv/deploy-portal
  repo: https://github.com/WikiOasis/mw-deploy.git
  rev: main
  php_version: "8.4"

  db:
    name: mwdeploy
    user: mwdeploy
    # Dedicated schema on the "other" mariadb host, not the db-c1 MediaWiki
    # cluster — see mariadb.portal_db (applied to db-other-us-east-011 via
    # salt/top.sls) for the database/user creation.
    host: db-other-us-east-011.ovvin.wonet

  # Salt minion id of the staging host. Every preparation step (git checkout,
  # patching, local rsync, staging canary) runs here — must match salt-key -L.
  staging_target: staging-us-east-021.ovvin.wonet

  # Bare rsync daemon module exported by mwdeploy.staging. Swap for an NFS path
  # if the farm grows an NFS export of the tree (single env var change, see
  # mw-deploy docs/SALT-INTEGRATION.md section 5).
  rsync_source: rsync://staging-us-east-021.ovvin.wonet/mediawiki/

  reverb:
    app_id: mwdeploy
    server_host: 127.0.0.1
    server_port: 8080
    public_host: console.wikioasis.org
    public_port: 443
    public_scheme: https

  rollout:
    default_parallel: 1
    max_parallel: 8
    canary_retries: 3
    l10n_wiki: testwiki

  # Where the tree-scan import screen looks, and where mw-config is checked
  # out relative to the deploy root it reads. config_dir is set-once per
  # farm: changing it after checkouts exist repoints where a removal is
  # aimed, not where the config lives, so treat an existing checkout as
  # needing a manual move first.
  scan:
    config_dir: config
    root: staging

  decisions:
    timeout: 900
    timeout_default: abort_and_rollback

  git_driver: salt
