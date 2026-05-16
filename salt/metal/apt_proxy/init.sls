# The apt proxy is only needed during initial provisioning to work around
# IPv6 failures. Once Salt manages this host, the proxy config is removed.
/etc/apt/apt.conf.d/99proxy:
  file.absent
