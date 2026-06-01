# OpenSearch's apt repo signing key uses SHA1 binding signatures, which sqv
# (used by apt on Ubuntu 24.04+) hard-rejects since 2026-02-01. For this
# internal cluster we bypass key verification with trusted=yes. Installation
# uses cmd.run so we can pass DISABLE_INSTALL_DEMO_CONFIG=true — required by
# the OpenSearch 2.12+ postinst to skip the demo TLS setup (moot here since
# the security plugin is disabled in opensearch.yml).

opensearch_apt_repo:
  file.managed:
    - name: /etc/apt/sources.list.d/opensearch.list
    - contents: |
        deb [trusted=yes arch=amd64] https://artifacts.opensearch.org/releases/bundle/opensearch/2.x/apt stable main
    - user: root
    - group: root
    - mode: '0644'

opensearch_pkg:
  cmd.run:
    - name: >
        apt-get update &&
        DISABLE_INSTALL_DEMO_CONFIG=true
        DISABLE_PERFORMANCE_ANALYZER_AGENT_CLI=true
        apt-get install -y opensearch
    - unless: dpkg -l opensearch 2>/dev/null | grep -q '^ii'
    - require:
      - file: opensearch_apt_repo

/etc/opensearch/opensearch.yml:
  file.managed:
    - source: salt://opensearch/files/opensearch.yml.jinja
    - template: jinja
    - user: root
    - group: opensearch
    - mode: '0660'
    - require:
      - cmd: opensearch_pkg

/etc/opensearch/jvm.options.d/heap.options:
  file.managed:
    - source: salt://opensearch/files/heap.options.jinja
    - template: jinja
    - user: root
    - group: opensearch
    - mode: '0660'
    - require:
      - cmd: opensearch_pkg

opensearch:
  service.running:
    - enable: True
    - watch:
      - file: /etc/opensearch/opensearch.yml
      - file: /etc/opensearch/jvm.options.d/heap.options
    - require:
      - cmd: opensearch_pkg
