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
#   sudo -u www-data /usr/bin/salt --batch 50% 'proxy*' test.ping
#   sudo -u www-data /usr/bin/salt --async 'staging-us-east-021' \
#       cmd.run_all 'mwdeploy-shim --version'
#   # then, using the JID printed above:
#   sudo -u www-data /usr/bin/salt 'staging-us-east-021' saltutil.find_job <jid>
# The portal's SaltClient runs with --batch (see pillar mwdeploy_portal
# rollout.default_parallel/max_parallel), and salt's batch runner pings every
# targeted minion with test.ping before dispatching the real job — so
# test.ping must be granted alongside cmd.run_all for every pattern below, or
# batched runs fail with AuthorizationError before cmd.run_all ever executes.
# If it works as root but not as www-data, fix the ACL/PKI permissions here —
# do not silently fall back to a passwordless sudo wrapper instead.
#
# --async support: `salt --async` still calls the same functions below (the
# ACL check is per-function, not per-client-mode), so cmd.run_all/test.ping
# already cover firing an async job. What --async changes is how the result
# comes back: the CLI returns the JID immediately instead of blocking, so
# checking on the job afterwards means a second call to saltutil.find_job
# against the same minions — that's granted alongside the others below, or
# every async status check fails with AuthorizationError even though the job
# itself ran fine.

/etc/salt/master.d/mwdeploy-acl.conf:
  file.managed:
    - contents: |
        publisher_acl:
          www-data:
            - 'mw*':
              - cmd.run_all
              - test.ping
              - saltutil.find_job
            - 'task*':
              - cmd.run_all
              - test.ping
              - saltutil.find_job
            - 'staging*':
              - cmd.run_all
              - test.ping
              - saltutil.find_job
            - 'proxy*':
              - cmd.run_all
              - test.ping
              - saltutil.find_job

        # Required for a non-root user (www-data) to read the master's PKI and
        # cache directories when publishing jobs via publisher_acl. This only
        # stops the master from clamping those directories back to 0700 on
        # start — it grants nothing by itself. The actual grant is the `salt`
        # group membership and directory modes below; without those, www-data
        # still gets AuthorizationError/permission-denied even though this is
        # set to True.
        permissive_pki_access: True
    # Keep this root:root. salt-master runs as root but with CAP_DAC_OVERRIDE
    # dropped, so it only reads this file via the owning-user permission bits,
    # not the root-bypasses-all-DAC-checks path. Owning it as `salt` (a group
    # the master process isn't in) makes the master itself unable to read its
    # own drop-in and fail to start with EACCES.
    #
    # Must stay non-writable by anyone but root: this file *is* www-data's
    # privilege boundary, so a world-writable copy lets www-data grant itself
    # anything. (A prior "0777" here didn't fix any real permission problem —
    # the master only ever needed to *read* it as its owning user — and it
    # reopened exactly the escalation this ACL exists to prevent.)
    - user: root
    - group: root
    - mode: '0644'

# The `salt` system group is what permissive_pki_access above relies on: it
# tells the master not to reset /etc/salt/pki/master and /var/cache/salt/master
# back to 0700 root:root on start, but something still has to grant www-data
# actual read/write access to them, or every `sudo -u www-data salt ...`
# fails (test.ping included) with a permission error before the ACL is even
# consulted. This group is that grant.
salt-group:
  group.present:
    - name: salt
    - system: True
    - addusers:
      - www-data

# Read+execute so www-data can load the master's private key material to
# authenticate published jobs. This is the same private key salt-master
# itself uses, so this grant is exactly as sensitive as it looks - see the
# cmd.run_all note at the top of this file.
/etc/salt/pki/master:
  file.directory:
    - group: salt
    - dir_mode: '0750'
    - file_mode: '0640'
    - recurse:
      - group
      - mode
    - require:
      - group: salt-group

# Read+write so www-data can create/read job and minion-cache data when
# publishing jobs (this is where --batch's per-minion test.ping results and
# the subsequent cmd.run_all results land).
/var/cache/salt/master:
  file.directory:
    - group: salt
    - dir_mode: '0770'
    - file_mode: '0660'
    - recurse:
      - group
      - mode
    - require:
      - group: salt-group

salt-master:
  service.running:
    - enable: True
    - watch:
      - file: /etc/salt/master.d/mwdeploy-acl.conf
