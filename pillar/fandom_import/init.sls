fandom_import:
  spool_dir: /srv/fandom-import
  venv: /opt/fandom-import/venv
  wikiteam3_version: '4.4.10'
  central_wiki: metawiki
  php: /usr/bin/php
  mwscript: /srv/mediawiki/scripts/mwscript.php
  user_agent: "WikiOasisFandomImport/1.0 (+https://meta.wikioasis.org/wiki/Special:FandomImport)"
  image_delay: 1.0
  retries: 5
  max_stage_attempts: 3
  min_free_bytes: 10737418240
  disk_headroom_bytes: 5368709120
  failed_retention_days: 3
  log_retention_days: 30
  dump_recheck_hours: 24
  dump_max_wait_days: 14
  prefer_full_history: True
