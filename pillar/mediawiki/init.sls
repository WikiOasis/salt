mediawiki:
  # System user used for SSH-based rsync and HAProxy commands
  deploy_user: mwdeploy

  # Paths
  staging_path: /srv/mediawiki-staging
  prod_path: /srv/mediawiki

  # Virtual host used for canary checks
  canary_vhost: test.wikioasis.org

  # Log file written on the staging/deploy server
  log_file: /var/log/mwdeploy.log

  # HAProxy backend name that holds the mw* servers
  haproxy_backend: mediawiki

  # Path to the HAProxy stats socket on proxy servers
  haproxy_socket: /run/haproxy/admin.sock

  # MediaWiki application servers (names must match SSH hostnames)
  mw_servers: []
  #  - mw-us-east-011
  #  - mw-us-east-021

  # HAProxy / proxy servers mwdeploy will SSH to for depool/repool
  proxy_servers: []
  #  - proxy-us-east-011

  # SSH public key for the mwdeploy user on the staging server.
  # Generate once on staging-us-east-021:
  #   sudo -u mwdeploy ssh-keygen -t ed25519 -f /home/mwdeploy/.ssh/id_ed25519 -N ''
  # Then paste the contents of /home/mwdeploy/.ssh/id_ed25519.pub here.
  deploy_ssh_public_key: ""

  # Webhook URLs for deployment notifications.
  # Leave empty to disable. Use --no-log to suppress all webhook posts.
  webhooks:
    discord: ""
    slack: ""
