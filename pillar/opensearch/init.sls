opensearch:
  cluster_name: wikioasis-search
  heap_size: 3g
  http_port: 9200
  transport_port: 9300
  nodes:
    - name: opensearch-us-east-011
      host: opensearch-us-east-011.ovvin.wonet
    - name: opensearch-us-east-012
      host: opensearch-us-east-012.ovvin.wonet
