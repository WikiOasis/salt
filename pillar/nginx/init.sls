nginx:
  server_blocks:
    - listen:
        - "80"
        - "[::]:80"
      server_name: ".wikioasis.org .skywiki.org .betaoasis.xyz"