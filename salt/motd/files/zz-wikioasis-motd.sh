# WikiOasis MOTD — managed by Salt (salt/motd). Do not edit by hand.
#
# Sourced by login shells via /etc/profile. Debian's pam_motd does not execute
# /etc/update-motd.d, so we render the banner here instead. Only fires for
# interactive shells attached to a terminal, so scp/rsync/`ssh host cmd` stay
# quiet. This file is sourced (not executed): never call exit here.

if [ -n "${PS1-}" ] && [ -t 1 ] && [ -x /usr/local/sbin/wikioasis-motd ]; then
    /usr/local/sbin/wikioasis-motd
fi
