mediawiki:
  deploy_user: mwdeploy
  staging_path: /srv/mediawiki-staging
  prod_path: /srv/mediawiki
  canary_vhost: test.wikioasis.org
  log_file: /var/log/mwdeploy.log
  haproxy_backend: mediawiki
  haproxy_socket: /run/haproxy/admin.sock
  backup_path: /srv/mediawiki-backup
  mw_servers: ['task-us-east-011.ovvin.wonet', 'mw-us-east-011.ovvin.wonet', 'mw-us-east-012.ovvin.wonet', 'mw-us-east-021.ovvin.wonet', 'mw-us-east-022.ovvin.wonet']
  proxy_servers: ['proxy-us-east-011.ovvin.wonet', 'proxy-us-east-021.ovvin.wonet']
  deploy_ssh_public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBw+m6ZQT6Q7MPgfd5STamRLSUADflff/9uKVtbBZluM mwdeploy@staging-us-east-021"
  # Path to the private key on the staging server; used by mwdeploy for all SSH/rsync
  ssh_identity: /home/mwdeploy/.ssh/id_ed25519
  webhooks:
    discord: ""
    slack: ""
