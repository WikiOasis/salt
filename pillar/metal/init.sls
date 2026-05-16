server_groups:
  - ops

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
  ipv6_prefix: "2604:2dc0:100:295c"
  ipv6_gateway: "2604:2dc0:100:29ff:ff:ff:ff:ff"
  public_bridge: "vmbr0"
  private_bridge: "vmbr-vrack"
  hosts:
    metal-us-east-01:
      vm_gateway_ll: "fe80::d250:99ff:feda:8f81"
    metal-us-east-02:
      vm_gateway_ll: "fe80::d250:99ff:feda:9205"
  vms:
    # metal-us-east-01
    bastion-us-east-011:
      metal_host: metal-us-east-01
      vmid: 101
      interface: ens18
    proxy-us-east-011:
      metal_host: metal-us-east-01
      vmid: 102
      interface: ens18
    # metal-us-east-02
    bastion-us-east-021:
      metal_host: metal-us-east-02
      vmid: 201
      interface: ens18
    proxy-us-east-021:
      metal_host: metal-us-east-02
      vmid: 202
      interface: ens18
    salt-us-east-021:
      metal_host: metal-us-east-02
      vmid: 210
      interface: ens18
