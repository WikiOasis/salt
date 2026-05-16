server_groups:
  - ops

# HTTP proxy for use during initial VM provisioning when IPv6 may be unavailable.
# Set Acquire::http::Proxy to this value in /etc/apt/apt.conf.d/99proxy on the VM.
# Salt enforces that file absent once it manages the host.
apt_bootstrap:
  http_cache: http://127.0.0.1:3128

metal_public_ips:
  - 40.160.53.92
  - 40.160.53.94

dns_hosts:
  bastion-us-east-011:
    ip: 10.0.1.49
    mac: bc:24:11:5e:84:0e
  proxy-us-east-011:
    ip: 10.0.1.2
    mac: bc:24:11:7f:59:ff
  db-other-us-east-011:
    ip: 10.0.1.20
    mac: bc:24:11:24:40:36
  bastion-us-east-021:
    ip: 10.0.2.49
    mac: bc:24:11:ab:a4:70
  salt-us-east-021:
    ip: 10.0.2.124
    mac: bc:24:11:e4:0b:97
  proxy-us-east-021:
    ip: 10.0.2.2
    mac: bc:24:11:90:a6:bd

proxmox:
  public_bridge: "vmbr0"
  private_bridge: "vmbr-vrack"
  hosts:
    metal-us-east-01:
      ipv6_prefix: "2604:2dc0:100:295c"
      ipv6_gateway: "2604:2dc0:100:29ff:ff:ff:ff:ff"
      vm_gateway_ll: "fe80::d250:99ff:feda:8f81"
    metal-us-east-02:
      ipv6_prefix: "2604:2dc0:100:295e"
      ipv6_gateway: "2604:2dc0:100:29ff:ff:ff:ff:ff"
      vm_gateway_ll: "fe80::d250:99ff:feda:9205"
  vms:
    # metal-us-east-01
    bastion-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 101
      interface: ens18
    proxy-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 102
      interface: ens18
    db-other-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 120
    # metal-us-east-02
    bastion-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 201
      interface: ens18
    proxy-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 202
      interface: ens18
    salt-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 210
      interface: ens18
