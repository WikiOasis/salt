opensearch_apt_key:
  cmd.run:
    - name: curl -fsSL https://artifacts.opensearch.org/publickeys/opensearch.pgp | gpg --dearmor -o /usr/share/keyrings/opensearch-keyring.gpg
    - creates: /usr/share/keyrings/opensearch-keyring.gpg

opensearch_apt_repo:
  file.managed:
    - name: /etc/apt/sources.list.d/opensearch.list
    - contents: |
        deb [signed-by=/usr/share/keyrings/opensearch-keyring.gpg arch=amd64] https://artifacts.opensearch.org/releases/bundle/opensearch/2.x/apt stable main
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - cmd: opensearch_apt_key

opensearch_pkg:
  pkg.installed:
    - name: opensearch
    - refresh: True
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
      - pkg: opensearch_pkg

/etc/opensearch/jvm.options.d/heap.options:
  file.managed:
    - source: salt://opensearch/files/heap.options.jinja
    - template: jinja
    - user: root
    - group: opensearch
    - mode: '0660'
    - require:
      - pkg: opensearch_pkg

opensearch:
  service.running:
    - enable: True
    - watch:
      - file: /etc/opensearch/opensearch.yml
      - file: /etc/opensearch/jvm.options.d/heap.options
    - require:
      - pkg: opensearch_pkg