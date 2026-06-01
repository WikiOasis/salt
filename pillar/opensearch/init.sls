opensearch:
  cluster_name: wikioasis-search
  heap_size: 3g
  # Throwaway password required by OpenSearch 2.12+ postinst; security plugin
  # is disabled in opensearch.yml so this credential is never active.
  initial_admin_password: "Wikioasis-OS-01!"
  http_port: 9200
  transport_port: 9300
  nodes:
    - name: opensearch-us-east-011
      host: opensearch-us-east-011.ovvin.wonet
    - name: opensearch-us-east-012
      host: opensearch-us-east-012.ovvin.wonet
