# Start user IDs at 3000 to avoid conflicts with already existing users
users:
    thomas:
        fullname: Thomas
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBBENCQ1Vgjdl8ux9snbGF4s1SRbcU0EvaYlj7I51LWG zippybonzo@wikioasis.org
        uid: 3000
        gid: 3000
    unai:
        fullname: Unai
        ssh-keys:
          - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICvwM20uHONQHh289mWK8VnvAod4FbuwML2gtyy8uBwj
        uid: 3001
        gid: 3001
groups:
    ops:
        gid: 7000
        description: root, on all servers
        members: [thomas, unai]
        privileges: ['ALL = (ALL) NOPASSWD: ALL']
    mediawiki-admins:
        gid: 7001
        description: elevated permissions on webservers
        members: []
        privileges: ['ALL = (www-data) NOPASSWD: ALL',
                'ALL = (ALL) NOPASSWD: /usr/sbin/service nginx *',
                'ALL = (ALL) NOPASSWD: /usr/sbin/service php8.4-fpm *',
                'ALL = (ALL) NOPASSWD: /bin/journalctl *']
