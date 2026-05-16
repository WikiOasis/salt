public_ip: 40.160.53.92

ip_forwarding:
  - host_port: 2322
    vm_dns: bastion-us-east-011.ovvin.wonet
    vm_ip: 10.0.1.49
    vm_port: 22
    proto: tcp
  - host_port: 80
    vm_dns: proxy-us-east-021.ovvin.wonet
    vm_ip: 10.0.1.2
    vm_port: 80
    proto: tcp
