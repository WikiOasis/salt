mwdeploy-legacy-retired:
  file.absent:
    - names:
      - /usr/local/bin/mwdeploy
      - /etc/mwdeploy
      - /var/log/mwdeploy-state.json
      - /etc/sudoers.d/mwdeploy_staging
      - /etc/sudoers.d/mwdeploy_target
