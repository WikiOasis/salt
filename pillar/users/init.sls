# Start user IDs at 3000 to avoid conflicts with already existing users
users:
    thomas:
        fullname: Thomas
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBENCQ1Vgjdl8ux9snbGF4s1SRbcU0EvaYlj7I51LWG zippybonzo@wikioasis.org
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDCEy/PIhExYwD6FYZoTARuajgaUuXGDJQVWJjKJQpVI zippybonzo@wikioasis.org
        uid: 3000
        gid: 3000
    unai:
        fullname: Unai
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICvwM20uHONQHh289mWK8VnvAod4FbuwML2gtyy8uBwj
        uid: 3001
        gid: 3001
    tali64:
        fullname: Tali64
        uid: 3002
        gid: 3002
    pisces:
        fullname: Pisces
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAKWvAxYvkaVdWezSktHSkz7LelSH+kOSaEkJclwkrM/ pisces@wikioasis
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFRow/qpcyGrFZUmHo91Q3yhq399X0Ig+xSR8IkBdd4D pisces@wikioasis+side
        uid: 3003
        gid: 3003
    reception:
        fullname: Reception123
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMQPuGdtuEkafBFAztzF8XMk06bmYVfe6ZDM14cvqUXU ed25519-key-20260803
        uid: 3004
        gid: 3004
groups:
    ops:
        gid: 7000
        description: root, on all servers
        members: [thomas, unai, reception]
        privileges: ['ALL = (ALL) NOPASSWD: ALL']
    mediawiki-admins:
        gid: 7001
        description: elevated permissions on webservers
        members: [pisces]
        privileges: ['ALL = (www-data) NOPASSWD: ALL',
                'ALL = (ALL) NOPASSWD: /usr/local/bin/mwdeploy *',
                'ALL = (ALL) NOPASSWD: /usr/sbin/service nginx *',
                'ALL = (ALL) NOPASSWD: /usr/sbin/service php8.4-fpm *',
                'ALL = (ALL) NOPASSWD: /bin/journalctl *']
