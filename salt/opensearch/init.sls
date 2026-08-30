{%- set cfg = salt['pillar.get']('opensearch', {}) %}
{%- set os_version = cfg.get('version', '1.3.20') %}
{%- set plugins = cfg.get('plugins', []) %}

# OpenSearch's apt repo signing key uses SHA1 binding signatures, which sqv
# (used by apt on Debian 13 / Ubuntu 24.04+) hard-rejects since 2026-02-01.
# For this internal cluster we bypass key verification with trusted=yes.

opensearch_apt_repo:
  file.managed:
    - name: /etc/apt/sources.list.d/opensearch.list
    - contents: |
        deb [trusted=yes arch=amd64] https://artifacts.opensearch.org/releases/bundle/opensearch/1.x/apt stable main
    - user: root
    - group: root
    - mode: '0644'

# Pinned to an exact patch release rather than 1.3.*: the search plugins below
# are built against one specific OpenSearch version and refuse to load on any
# other, so the two have to move together.
opensearch_pkg:
  cmd.run:
    - name: apt-get update && apt-get install -y --allow-downgrades opensearch={{ os_version }}
    - env:
      - DEBIAN_FRONTEND: noninteractive
      - DISABLE_INSTALL_DEMO_CONFIG: "true"
      - DISABLE_PERFORMANCE_ANALYZER_AGENT_CLI: "true"
    - unless: "dpkg-query -W -f='${Version}' opensearch 2>/dev/null | grep -qx '{{ os_version }}'"
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

opensearch_plugin_archives:
  file.directory:
    - name: /opt/opensearch-plugins
    - user: root
    - group: root
    - mode: '0755'

{%- for plugin in plugins %}
{#- A plugin with no version is a stock one, installed by name so that
    opensearch-plugin resolves it to the running node's version. Anything with
    a version or an explicit url is fetched as a zip and installed from disk. #}
{%- set pinned = plugin.get('version') or plugin.get('url') %}
{%- set pversion = plugin.get('version', os_version) %}
{%- if pinned %}
{%- set maven_path = plugin.get('maven_path', 'org/wikimedia/search/' ~ plugin.name) %}
{%- set artifact = maven_path.split('/') | last %}
{%- set maven_url = 'https://repo1.maven.org/maven2/' ~ maven_path ~ '/' ~ pversion ~ '/' ~ artifact ~ '-' ~ pversion ~ '.zip' %}
{%- set url = plugin.get('url', maven_url) %}
{%- set archive = '/opt/opensearch-plugins/' ~ artifact ~ '-' ~ pversion ~ '.zip' %}
{%- set install_target = 'file://' ~ archive %}

opensearch_plugin_archive_{{ plugin.name }}:
  file.managed:
    - name: {{ archive }}
    - source: {{ url }}
    # Maven Central publishes a bare-hash .sha512 next to every artifact, which
    # Salt reads directly. Anything hosted elsewhere pins its hash in pillar.
    - source_hash: {{ plugin.get('source_hash', maven_url ~ '.sha512') }}
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - file: opensearch_plugin_archives
{%- else %}
{%- set install_target = plugin.name %}
{%- endif %}

# opensearch-plugin has no in-place upgrade, so drop any older copy first. The
# remove is expected to fail on a first install; only the install's exit status
# decides whether the state succeeded.
opensearch_plugin_{{ plugin.name }}:
  cmd.run:
    - name: >-
        /usr/share/opensearch/bin/opensearch-plugin remove {{ plugin.name }} 2>/dev/null;
        /usr/share/opensearch/bin/opensearch-plugin install --batch {{ install_target }}
    - env:
      - OPENSEARCH_PATH_CONF: /etc/opensearch
    - unless: "grep -qxF 'version={{ pversion }}' /usr/share/opensearch/plugins/{{ plugin.name }}/plugin-descriptor.properties"
    - require:
      - cmd: opensearch_pkg
{%- if pinned %}
      - file: opensearch_plugin_archive_{{ plugin.name }}
{%- endif %}
{%- endfor %}

opensearch:
  service.running:
    - enable: True
    - watch:
      - file: /etc/opensearch/opensearch.yml
      - file: /etc/opensearch/jvm.options.d/heap.options
{%- for plugin in plugins %}
      - cmd: opensearch_plugin_{{ plugin.name }}
{%- endfor %}
    - require:
      - cmd: opensearch_pkg
