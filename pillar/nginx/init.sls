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

  custom_domains:
    25minresearchwiki:
      server_name: '25minresearch.com'
      listen: 80
      location: 'W4caqz7eaA6whhuiOJpfXFjJAlVtzQ8_jFy8pMWytf_cB4WHCYsiXdYFnkhNr__v'
      return: 'W4caqz7eaA6whhuiOJpfXFjJAlVtzQ8_jFy8pMWytf_cB4WHCYsiXdYFnkhNr__v.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: '25minresearchwiki'
    allgamesbackloggdwiki:
      server_name: 'allgamesbackloggd.giize.com'
      listen: 80
      location: 'BGsba513QBfhkV74c2U-kQ'
      return: 'BGsba513QBfhkV74c2U-kQ.qG9fjZxG01eSzr9qiXla3XyRCJN2bTBpnbqSuwD-NAs'
      database_name: 'allgamesbackloggdwiki'
    antecedentswiki:
      server_name: 'www.antecedents.xyz'
      listen: 80
      location: 'Bh0ZAAyEgSf3RU_WOkJROAxRgeiiJb2mDQ95aMLpSLI'
      return: 'Bh0ZAAyEgSf3RU_WOkJROAxRgeiiJb2mDQ95aMLpSLI.3jpn2Xqo6p5__tIrATrzlRSQyozvu9qIdOC4Js-jV9U'
      database_name: 'antecedentswiki'
    b1ackwiki:
      server_name: 'wiki.b1ack.net'
      listen: 80
      location: '9EXYIm9fsCIePQxLnhr3poxESHGfcYuuwHfxAXZNndMw_pbr9v6dcJa8ItTWz_zi'
      return: '9EXYIm9fsCIePQxLnhr3poxESHGfcYuuwHfxAXZNndMw_pbr9v6dcJa8ItTWz_zi.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'b1ackwiki'
    biteismewiki:
      server_name: 'biteisme.com'
      listen: 80
      location: 'yD3yUuglMrj-4k6nSrXIyaBS2ynVhP4hlZ4dCTrSMu6F_B4_dXekqAPRvEtE_U49'
      return: 'yD3yUuglMrj-4k6nSrXIyaBS2ynVhP4hlZ4dCTrSMu6F_B4_dXekqAPRvEtE_U49.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'biteismewiki'
    br3xawikiwiki:
      server_name: 'wiki.br3xality.org'
      listen: 80
      location: 'sqq2IDKog7EfGaQf0m6GZ8d0sFR332oMtl7xDQORahVCHABdaPyWpxX9qMTm9naq'
      return: 'sqq2IDKog7EfGaQf0m6GZ8d0sFR332oMtl7xDQORahVCHABdaPyWpxX9qMTm9naq.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'br3xawikiwiki'
    cognwiki:
      server_name: 'wiki.cogn.io.vn'
      listen: 80
      location: 'cmf02VxOrmbd43LQEeTVfaQiWee4p6ixMQh0LEAXVfQkfgm4LZxd1HQ-SIlHDbZD'
      return: 'cmf02VxOrmbd43LQEeTVfaQiWee4p6ixMQh0LEAXVfQkfgm4LZxd1HQ-SIlHDbZD.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'cognwiki'
    combustlemwiki:
      server_name: 'wiki.combustlem.co.uk'
      listen: 80
      location: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp'
      return: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'combustlemwiki'
    creativewikiswiki:
      server_name: 'creativewikis.skywiki.org'
      listen: 80
      location: 'WB0Ufc4IAeVDdl6JfwTyKj-ETgUqGa8KI-12S-mN_E5y1omHfppBMTUN7NTU78zG'
      return: 'WB0Ufc4IAeVDdl6JfwTyKj-ETgUqGa8KI-12S-mN_E5y1omHfppBMTUN7NTU78zG.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'creativewikiswiki'
    drawingwiki:
      server_name: 'www.drawing.wiki'
      listen: 80
      location: '0mxcwTJibfwKVSeAYeUb2O5T1WSgC5DnrHdjqOYM98d6LIpjlSj0NIsLkE7qL_Qi'
      return: '0mxcwTJibfwKVSeAYeUb2O5T1WSgC5DnrHdjqOYM98d6LIpjlSj0NIsLkE7qL_Qi.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'drawingwiki'
    esuwiki:
      server_name: 'esuwiki.wiki'
      listen: 80
      location: '2cMH9ZDTV_IfNXZfPCJ5TpWI39xrKGZ3NqjSGUtXGdtXsAb9PTYMgKEJULmR7kk6'
      return: '2cMH9ZDTV_IfNXZfPCJ5TpWI39xrKGZ3NqjSGUtXGdtXsAb9PTYMgKEJULmR7kk6.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'esuwiki'
    founderswiki:
      server_name: 'founderswiki.org'
      listen: 80
      location: 'IJ-1fjqpSYrfiX5G8X0_GNbyejpNSiC5asVhHh1rlwPSPzsmGcAFT9aPZwGsax07'
      return: '0mxcwTJibfwKVSeAYeUb2O5T1WSgC5DnrHdjqOYM98d6LIpjlSj0NIsLkE7qL_Qi.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'founderswiki'
    freshwebsiteswiki:
      server_name: 'freshwebsites.skywiki.org'
      listen: 80
      location: 'EZQDzRwzkbZa7zGrPP5Buh_nm8HmS7B-FJ_THBLs2ZT6LzXWTrkuSy67zitIOn0i'
      return: 'EZQDzRwzkbZa7zGrPP5Buh_nm8HmS7B-FJ_THBLs2ZT6LzXWTrkuSy67zitIOn0i.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'freshwebsiteswiki'
    hisdarkmaterialswiki:
      server_name: 'hdm-wiki.de'
      listen: 80
      location: 'AJY8rOPeI4BLR9G2i9kTwg'
      return: 'AJY8rOPeI4BLR9G2i9kTwg.l7gwszJvNB4zDQrUoNIf3VaGZN3Ffz4XMnMkYM0h9m4'
      database_name: 'hisdarkmaterialswiki'
    oaklandswiki:
      server_name: 'oaklandswiki.com'
      listen: 80
      location: 'VbBGzCuJIgOFt-q15qQbe8MTwIORA0MopOschmOqyzB54wtFewAkRBGaQHJoqRL-'
      return: 'VbBGzCuJIgOFt-q15qQbe8MTwIORA0MopOschmOqyzB54wtFewAkRBGaQHJoqRL-.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'oaklandswiki'
    objectshowpediawiki:
      server_name: 'www.objectshowpedia.com'
      listen: 80
      location: 'placeholder'
      return: 'placeholder'
      database_name: 'objectshowpediawiki'
    poniuswiki:
      server_name: 'projects.ponius.com'
      listen: 80
      location: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp'
      return: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'poniuswiki'
    progressivismwiki:
      server_name: 'wiki.progressivism.lgbt'
      listen: 80
      location: 'Jz1nSIZSku7hKy8pFRYckwtGU1PsKjeDnOtToR5qEYJoR-YwYBrt1ctFnJDUiJJr'
      return: 'Jz1nSIZSku7hKy8pFRYckwtGU1PsKjeDnOtToR5qEYJoR-YwYBrt1ctFnJDUiJJr.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'progressivismwiki'
    projectconfusciusidwiki:
      server_name: 'wiki.projectconfucius.id'
      listen: 80
      location: 'mIeld9_l2-dBbmIXTarQhivdX_c9HiW_4zp06CLRDnDWtqeR3T6JhNo052EPU4Ov'
      return: 'mIeld9_l2-dBbmIXTarQhivdX_c9HiW_4zp06CLRDnDWtqeR3T6JhNo052EPU4Ov.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'projectconfusciusidwiki'
    projectherzlwiki:
      server_name: 'wiki.projectherzl.com'
      listen: 80
      location: 'tg7JuUqB_fluu0hJtBU8vvJVezi2Y_WWGu_VSBY9JAS_wR-TVurAABRlbo87X7Ab'
      return: 'tg7JuUqB_fluu0hJtBU8vvJVezi2Y_WWGu_VSBY9JAS_wR-TVurAABRlbo87X7Ab.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'projectherzlwiki'
    rottenwebsiteswiki:
      server_name: 'rottenwebsites.skywiki.org'
      listen: 80
      location: 'tCD37NuP2lyNT7B8-BJ8362nvraYh6f4gOfLlgO4o_NBIl3KVC3awHvHv11q1IqJ'
      return: 'tCD37NuP2lyNT7B8-BJ8362nvraYh6f4gOfLlgO4o_NBIl3KVC3awHvHv11q1IqJ.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'rottenwebsiteswiki'
    skywikiwiki:
      server_name: 'meta.skywiki.org'
      listen: 80
      location: 'Xv9Nog_ecPGt3o95FJJGpne4YRUWptxXXpA6By-sZROTt-OtlWfEU53i6Ken7DBr'
      return: 'Xv9Nog_ecPGt3o95FJJGpne4YRUWptxXXpA6By-sZROTt-OtlWfEU53i6Ken7DBr.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'skywikiwiki'
    solarpunkwiki:
      server_name: 'www.solarpunk.wiki'
      listen: 80
      location: 'py_SqqfZnDI2q2LQkLUXETagCWz_XKLJfUavp8ncbmFlNaxrJ9RCTR1nt6bBLVdh'
      return: 'py_SqqfZnDI2q2LQkLUXETagCWz_XKLJfUavp8ncbmFlNaxrJ9RCTR1nt6bBLVdh.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'solarpunkwiki'
    songnguwiki:
      server_name: 'meta.songngu.xyz'
      listen: 80
      location: '6I1P6k92xqWHnIS2VHpCUu3Yr7MwXcfD9O8R9KKs-gYDKxzdfd2Zm09koRVC1WIh'
      return: '6I1P6k92xqWHnIS2VHpCUu3Yr7MwXcfD9O8R9KKs-gYDKxzdfd2Zm09koRVC1WIh.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'songnguwiki'
    statskalenderwiki:
      server_name: 'statskalender.se'
      listen: 80
      location: '5D5Mck-DtN9WFJufPmFpMqWlbac7pQP0DSg8pIzCAVHGnpcQ2BRGZKX6F3BAyiSx'
      return: '5D5Mck-DtN9WFJufPmFpMqWlbac7pQP0DSg8pIzCAVHGnpcQ2BRGZKX6F3BAyiSx.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'statskalenderwiki'
    tgdpandrcwiki:
      server_name: 'wiki.thatgamedev.qzz.io'
      listen: 80
      location: 'p_DvNS30HPldPoLL5WAsyIk1pQ_ACbgJH7RBFqSdQjeudyjNvj6GdH6T7G4BgDnr'
      return: 'p_DvNS30HPldPoLL5WAsyIk1pQ_ACbgJH7RBFqSdQjeudyjNvj6GdH6T7G4BgDnr.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'tgdpandrcwiki'
    thaeciawiki:
      server_name: 'wiki.thaecia.eu'
      listen: 80
      location: 'tg7JuUqB_fluu0hJtBU8vvJVezi2Y_WWGu_VSBY9JAS_wR-TVurAABRlbo87X7Ab'
      return: 'tg7JuUqB_fluu0hJtBU8vvJVezi2Y_WWGu_VSBY9JAS_wR-TVurAABRlbo87X7Ab.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'thaeciawiki'
    thefireplacewiki:
      server_name: 'www.thefireplace.info'
      listen: 80
      location: 'zLAeko99RYIk3sQ-XZlaoUBaKzDvYdUKhMTGR6MIqs_-6ovprep3IiTmI4MWoLUX'
      return: 'zLAeko99RYIk3sQ-XZlaoUBaKzDvYdUKhMTGR6MIqs_-6ovprep3IiTmI4MWoLUX.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'thefireplacewiki'
    thekinkyacademywiki:
      server_name: 'wiki.thekinkyacademy.cc'
      listen: 80
      location: 'VqzkM9gY4Vwmw_zZzxy3Oipvr4Lqv-JcMQRqJK2_AwE3c1wQBnPmjEgRtZMDMNJR'
      return: 'VqzkM9gY4Vwmw_zZzxy3Oipvr4Lqv-JcMQRqJK2_AwE3c1wQBnPmjEgRtZMDMNJR.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'thekinkyacademywiki'
    tiresomewikiswiki:
      server_name: 'tiresomewikis.skywiki.org'
      listen: 80
      location: 'WB0Ufc4IAeVDdl6JfwTyKj-ETgUqGa8KI-12S-mN_E5y1omHfppBMTUN7NTU78zG'
      return: 'WB0Ufc4IAeVDdl6JfwTyKj-ETgUqGa8KI-12S-mN_E5y1omHfppBMTUN7NTU78zG.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'tiresomewikiswiki'
    wellbornarchiveswiki:
      server_name: 'wiki.wellbornarchives.org'
      listen: 80
      location: 'uxVgOovs4JTDK6udZMvGePyWo7D-SiOc491x9zZN_RwYRNkJw3vVRyM80YaoVVK'
      return: 'uxVgOovs4JTDK6udZMvGePyWo7D-SiOc491x9zZN_RwYRNkJw3vVRyM80YaoVVK'
      database_name: 'wellbornarchiveswiki'
    wikigeniuswiki:
      server_name: 'wikigenius.org'
      listen: 80
      location: 'oMeC5SAmacMG-i00OK5dwocen0XgIVrS7hzwAbbh-ldxHuXfO7RKAv_l5G8cbbuz'
      return: 'oMeC5SAmacMG-i00OK5dwocen0XgIVrS7hzwAbbh-ldxHuXfO7RKAv_l5G8cbbuz.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'wikigeniuswiki'
    wikimicrowiki:
      server_name: 'wikimicro.com'
      listen: 80
      location: 'SDqmfnfpCp7VEZIoHKX60RJAlTXM5GqIdymaskj2t5C70AiQE9c0G00R_41G5cSJ'
      return: 'SDqmfnfpCp7VEZIoHKX60RJAlTXM5GqIdymaskj2t5C70AiQE9c0G00R_41G5cSJ.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'wikimicrowiki'
    zhcountryhumanswiki:
      server_name: 'zh.countryhumans.wiki'
      listen: 80
      location: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp'
      return: 'um9fLzxkEiHaiAi-fX5aMOjAdJ4o6p_mds9oIPU9CFU4Y-M_atyy5aswBhs5qpLp.r54qAqCZSs4xyyeamMffaxyR1FWYVb5OvwUh8EcrhpI'
      database_name: 'zhcountryhumanswiki'