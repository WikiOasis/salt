# Fleet-wide swappiness. 10 is a conservative server default: it keeps swap as
# a safety margin for genuinely cold pages instead of letting the kernel trade
# away page cache and resident working set under normal load, without disabling
# swap outright (0) and risking the OOM killer on a memory spike.
#
# Note this only changes future reclaim decisions -- pages already swapped out
# stay there until they are touched again or swap is cycled.
/etc/sysctl.d/99-swappiness.conf:
  file.managed:
    - contents: |
        vm.swappiness=10
    - user: root
    - group: root
    - mode: '0644'

apply_swappiness_sysctl:
  cmd.run:
    - name: sysctl -p /etc/sysctl.d/99-swappiness.conf
    - onchanges:
      - file: /etc/sysctl.d/99-swappiness.conf
