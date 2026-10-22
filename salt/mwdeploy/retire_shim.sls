mwdeploy-shim-retired:
  file.absent:
    - names:
      - /usr/local/bin/mwdeploy-shim
      - /etc/sudoers.d/mwdeploy
