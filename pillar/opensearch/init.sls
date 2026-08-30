opensearch:
  # Pinned exactly: OpenSearch plugins declare the opensearch.version they were
  # built against and refuse to load on any other version, so this must stay in
  # lockstep with the plugin versions below.
  version: 1.3.20
  cluster_name: wikioasis-search
  heap_size: 3g
  http_port: 9200
  transport_port: 9300
  nodes:
    - name: opensearch-us-east-011
      host: opensearch-us-east-011.ovvin.wonet
    - name: opensearch-us-east-012
      host: opensearch-us-east-012.ovvin.wonet

  # Plugins CirrusSearch (MediaWiki 1.46) knows how to use. The names here are
  # the names the plugin reports to _cat/plugins, which is what CirrusSearch
  # matches against -- see includes/Maintenance/Plugins.php in CirrusSearch,
  # which maps the Elasticsearch-era names onto these OpenSearch ones.
  #
  # An entry with no version is a stock OpenSearch plugin, installed by name;
  # opensearch-plugin resolves it to the running node's version. An entry with
  # a version is downloaded as a zip, checksummed, and installed from disk.
  plugins:

    # Stock OpenSearch analysis plugins.
    # analysis-icu is the big one: it gates $wgCirrusSearchNaturalTitleSort and
    # changes the analysis chain for most languages. The rest are per-language.
    - name: analysis-icu
    - name: analysis-smartcn     # zh
    - name: analysis-stempel     # pl
    - name: analysis-kuromoji    # ja
    - name: analysis-nori        # ko
    - name: analysis-ukrainian   # uk, superseded by extra-analysis-ukrainian below

    # Wikimedia plugins, published to Maven Central under org.wikimedia.search.
    # Version is <opensearch version>-wmf<n>; esperanto and serbian have no wmf
    # builds for 1.3.20, so they sit at the plain release version.
    - name: opensearch-extra
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-textify
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-homoglyph
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-khmer
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-slovak
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-turkish
      version: 1.3.20-wmf9
    - name: opensearch-extra-analysis-ukrainian
      version: 1.3.20-wmf9
    # These two predate Maven Central's .sha512 sidecars -- they ship only .md5
    # and .sha1 -- so pin a sha256 verified against the published .sha1.
    - name: opensearch-extra-analysis-esperanto
      version: 1.3.20
      source_hash: sha256=075b1e87291f1ed58652f99dea2aca0af0287e4c6be8aaaf16e5622b34f618cb
    - name: opensearch-extra-analysis-serbian
      version: 1.3.20
      source_hash: sha256=8529be8efffe7e47a1f2830a0a2a475fbdd3f03e67e6f9002220d7e6bd80a101

    # Also Wikimedia, but the artifact id differs from the plugin name and it
    # lives under a different group, so both are spelled out. Only used when
    # $wgCirrusSearchUseExperimentalHighlighter is enabled.
    - name: cirrus-highlighter
      version: 1.3.20-wmf5
      maven_path: org/wikimedia/search/highlighter/cirrus-highlighter-opensearch-plugin

    # Third party (INFINI Labs). Needed alongside analysis-smartcn for the
    # Chinese analysis chain. Not on Maven Central, so the URL and hash are
    # given explicitly.
    - name: analysis-stconvert
      version: 1.3.20
      url: https://release.infinilabs.com/analysis-stconvert/stable/opensearch-analysis-stconvert-1.3.20.zip
      source_hash: sha256=c64d039f16b23a1837e9a603131326a6e77fabcadfb63a259da43c4ce92761e8

    # Not installed: analysis-hebrew (he) has no published OpenSearch build,
    # and analysis-sudachi is an alternative to analysis-kuromoji for ja.
