public_ip: 40.160.53.94

ip_forwarding:
  - host_port: 2322
    vm_dns: bastion-us-east-021.ovvin.wonet
    vm_ip: 10.0.2.49
    vm_port: 22
    proto: tcp
  - host_port: 80
    vm_dns: proxy-us-east-021.ovvin.wonet
    vm_ip: 10.0.2.2
    vm_port: 80
    proto: tcp
  - host_port: 33060
    vm_dns: db-c1-us-east-021.ovvin.wonet
    vm_ip: 10.0.2.20
    vm_port: 3306
    proto: tcp
