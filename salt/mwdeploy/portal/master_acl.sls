# The security decision in this whole integration: what www-data (the portal,
# via app/Services/SaltClient) is allowed to do with the local `salt` binary.
#
# publisher_acl is Salt's own mechanism and the only one that actually narrows
# the grant, per mw-deploy's docs/SALT-INTEGRATION.md section 4 "Option A".
# Be honest about the limit: cmd.run_all is arbitrary command execution on
# whatever minions are listed below — the ACL bounds *which minions* and
# *which Salt function*, not what runs inside it. mwdeploy-shim is the
# intended surface, not an enforced one. A custom execution module exposing
# only mwdeploy.* verbs (so the grant narrows to those verbs specifically) is
# flagged there as a genuine follow-up, not attempted here — it needs a
# matching SaltClient change in the portal itself.
#
# Verify before trusting the UI:
#   sudo -u www-data /usr/bin/salt 'staging-us-east-021' test.ping
#   sudo -u www-data /usr/bin/salt --out=json --static 'staging-us-east-021' \
#       cmd.run_all 'mwdeploy-shim --version'
# If it works as root but not as www-data, fix the ACL/PKI permissions here —
# do not silently fall back to a passwordless sudo wrapper instead.

/etc/salt/master.d/mwdeploy-acl.conf:
  file.managed:
    - contents: |
        publisher_acl:
          www-data:
            - 'mw*':
              - cmd.run_all
            - 'task*':
              - cmd.run_all
            - 'staging*':
              - cmd.run_all
            - 'proxy*':
              - cmd.run_all

        # Required for a non-root user (www-data) to read the master's PKI and
        # cache directories when publishing jobs via publisher_acl.
        permissive_pki_access: True
    # Keep this root:root. salt-master runs as root but with CAP_DAC_OVERRIDE
    # dropped, so it only reads this file via the owning-user permission bits,
    # not the root-bypasses-all-DAC-checks path. Owning it as `salt` (a group
    # the master process isn't in) makes the master itself unable to read its
    # own drop-in and fail to start with EACCES.
    - user: root
    - group: root
    - mode: '0644'

salt-master:
  service.running:
    - enable: True
    - watch:
      - file: /etc/salt/master.d/mwdeploy-acl.conf
