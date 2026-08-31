# Support triage bot NRPE check — apply to apps* servers via top.sls.
# Requires: nagios-nrpe-server and check_systemd_service.sh already on target
# (deployed by monitoring.nrpe_salt which runs on all hosts).
#
# The unit sets StartLimitBurst, so a bot that cannot start — a rotated token,
# an unreachable database — stops restarting and sits in `failed` rather than
# looping silently. This is what turns that into an alert: without it the only
# symptom is a support forum that has quietly stopped being triaged, which
# nobody notices until someone asks why their thread has no tags.

/etc/nagios/nrpe.d/wikioasis_support.cfg:
  file.managed:
    - source: salt://monitoring/files/nrpe/wikioasis_support.cfg
    - mode: '0644'
    - require:
      - file: /usr/lib/nagios/plugins/check_systemd_service.sh
    - watch_in:
      - service: nagios-nrpe-server
