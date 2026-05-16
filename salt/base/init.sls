set_timezone:
  timezone.system:
    - name: {{ salt['pillar.get']('timezone', 'Etc/UTC') }}
