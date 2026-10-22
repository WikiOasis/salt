slop:
  repo: https://github.com/WikiOasis/slop.git
  rev: main
  path: /opt/slop
  user: mwdeploy
  master: staging-us-east-021.ovvin.wonet
  config_repo: git@github.com:WikiOasis/slop-conf.git
  config_branch: main
  build_dirs:
    - /srv/mediawiki-build
    - /srv/tsportal-build
    - /srv/jobrunner-build
  live_path: /srv/mediawiki
  php_version: '8.4'
  units:
    - mediawiki-jobrunner
    - mediawiki-jobchron
    - tsportal-worker
  www_data_commands:
    - /usr/bin/php8.4 /srv/tsportal/artisan *
