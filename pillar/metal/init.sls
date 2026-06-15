# HTTP proxy for use during initial VM provisioning when IPv6 may be unavailable.
# Set Acquire::http::Proxy to this value in /etc/apt/apt.conf.d/99proxy on the VM.
# Salt enforces that file absent once it manages the host.
apt_bootstrap:
  http_cache: http://127.0.0.1:3129

metal_public_ips:
  - 40.160.53.92
  - 40.160.53.94

dns_hosts:
  metal-us-east-01:
    ip: 10.0.1.1
    mac: ~
  metal-us-east-02:
    ip: 10.0.2.1
    mac: ~
  bastion-us-east-011:
    ip: 10.0.1.49
    mac: bc:24:11:5e:84:0e
  proxy-us-east-011:
    ip: 10.0.1.2
    mac: bc:24:11:7f:59:ff
  db-other-us-east-011:
    ip: 10.0.1.20
    mac: bc:24:11:24:40:36
  db-pc-us-east-011:
    ip: 10.0.1.21
    mac: bc:24:11:d1:a6:37
  redis-us-east-011.ovvin.wonet:
    ip: 10.0.1.40
    mac: bc:24:11:9f:38:bc
  redis-us-east-012.ovvin.wonet:
    ip: 10.0.1.41
    mac: bc:24:11:68:d8:67
  opensearch-us-east-011.ovvin.wonet:
    ip: 10.0.1.50
    mac: bc:24:11:f7:31:4d
  opensearch-us-east-012.ovvin.wonet:
    ip: 10.0.1.51
    mac: bc:24:11:ch9:04:47
  mw-us-east-011.ovvin.wonet:
    ip: 10.0.1.60
    mac: bc:24:11:ac:18:e0
  mw-us-east-012.ovvin.wonet:
    ip: 10.0.1.61
    mac: bc:24:11:79:3a:be
  task-us-east-011.ovvin.wonet:
    ip: 10.0.1.65
    mac: bc:24:11:27:84:e8
  bastion-us-east-021:
    ip: 10.0.2.49
    mac: bc:24:11:ab:a4:70
  monitoring-us-east-021:
    ip: 10.0.2.3
    mac: bc:24:11:dd:30:d6
  salt-us-east-021:
    ip: 10.0.2.124
    mac: bc:24:11:e4:0b:97
  proxy-us-east-021:
    ip: 10.0.2.2
    mac: bc:24:11:90:a6:bd
  db-c1-us-east-021:
    ip: 10.0.2.20
    mac: bc:24:11:89:75:da
  mw-us-east-021.ovvin.wonet:
    ip: 10.0.2.60
    mac: bc:24:11:4c:80:6f
  mw-us-east-022.ovvin.wonet:
    ip: 10.0.2.61
    mac: bc:24:11:a0:00:bc
  staging-us-east-021.ovvin.wonet:
    ip: 10.0.2.65
    mac: bc:24:11:12:6a:a6
  apps-us-east-021.ovvin.wonet:
    ip: 10.0.2.70
    mac: bc:24:11:62:c2:3d

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
    redis-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 140
    redis-us-east-012.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 141
    opensearch-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 150
    opensearch-us-east-012.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 151
    mw-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 160
    mw-us-east-012.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 161
    task-us-east-011.ovvin.wonet:
      metal_host: metal-us-east-01
      vmid: 165
    # metal-us-east-02
    bastion-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 201
    proxy-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 202
    salt-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 210
    monitoring-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 203
    db-c1-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 220
    mw-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 260
    mw-us-east-022.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 261
    staging-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 265
    apps-us-east-021.ovvin.wonet:
      metal_host: metal-us-east-02
      vmid: 270
