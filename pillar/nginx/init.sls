nginx:
  doc_root: /srv/mediawiki

  csp_header: >-
    default-src 'self' https://*.betaoasis.xyz https://*.wikioasis.org;
    script-src 'self' blob: 'unsafe-inline' 'unsafe-eval' https://*.betaoasis.xyz https://*.wikioasis.org https://*.newrelic.com https://*.wikimedia.org https://*.wikipedia.org https://*.mediawiki.org https://*.sentry-cdn.com https://*.cloudflareinsights.com https://hcaptcha.com https://*.hcaptcha.com https://*.miraheze.org https://*.googletagmanager.com;
    style-src 'self' data: 'unsafe-inline' https://*.betaoasis.xyz https://*.wikioasis.org https://*.wikimedia.org https://*.wikipedia.org https://*.mediawiki.org https://*.sentry-cdn.com https://*.miraheze.org https://fonts.googleapis.com https://fonts.bunny.net;
    img-src 'self' data: blob: https://*.betaoasis.xyz https://upload.wikimedia.org https://*.wikioasis.org https://i.ytimg.com https://mirrors.creativecommons.org https://cdn.simpleicons.org https://i.imgur.com https://*.miraheze.org https://*.wikitide.net https://media.discordapp.net https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com https://*.g.doubleclick.net https://*.google.com https://*.gstatic.com https://www.gnu.org;
    font-src 'self' data: https://*.betaoasis.xyz https://*.wikioasis.org https://static.miraheze.org https://fonts.gstatic.com https://static.wikitide.net https://fonts.bunny.net;
    connect-src 'self' https://*.betaoasis.xyz https://*.wikioasis.org https://*.nr-data.net https://*.youtube-nocookie.com https://storage.googleapis.com https://*.wikimedia.org https://*.wikipedia.org https://*.mediawiki.org https://*.sentry-cdn.com https://*.ingest.us.sentry.io https://hcaptcha.com https://*.hcaptcha.com https://*.miraheze.org https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com https://*.g.doubleclick.net https://*.google.com;
    frame-src 'self' https://*.youtube-nocookie.com https://www.youtube.com https://hcaptcha.com https://*.hcaptcha.com https://static.cloudflareinsights.com;
    frame-ancestors 'self';
    form-action 'self' http://127.0.0.1:300 http://localhost:3000 https://*.betaoasis.xyz https://*.wikioasis.org;
    base-uri 'self';
    report-uri https://wikioasis.report-uri.com/r/d/csp/reportOnly;

  server_blocks:
    - listen:
        - "80"
        - "[::]:80"
      server_name: ".wikioasis.org .skywiki.org .betaoasis.xyz"