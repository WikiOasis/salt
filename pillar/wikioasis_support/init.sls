wikioasis_support:
  path: /srv/wikioasis-support
  user: wikioasis-support
  repo: https://github.com/WikiOasis/WikiOasisSupport.git
  rev: main
  node_version: 24.20.0
  log_level: info
    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------
  db:
    host: db-other-us-east-011.ovvin.wonet
    port: 3306
    name: wikioasis_support
    user: wikioasis_support

  triage:
    guild_id: '1299761391523205273'
    forum_channel_id: '1299763417472569345'
    board_channel_id: '1544077283139264616'

    support_roles:
      - '1300548216915234909'
      - '1300548280606003250'
      - '1544083908306403399'
      - '1300548239325401088'
    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------
    teams:
      - key: tech
        name: Technology Team
        role_id: '1300548216915234909'
        prompt: >-
          A confirmed technical issue, such as an outage, a serious bug that cannot be
          reported to Phorge, or any issue which requires backend server access to triage
          and help resolve. Do not send unconfirmed issues to this team, to avoid flooding
          them with unnecessary requests which they have limited manpower to handle.

      - key: stewards
        name: Stewards
        role_id: '1300548280606003250'
        prompt: >-
          An issue which may require a steward to opine, for example a question about a wiki
          request, a request to delete/modify wiki settings, or general farm maintenance.
          Avoid sending requests that are too general here, as steward presence should be
          reserved for when it is clear they and only they can help with the matter.

      - key: support
        name: Support Helpers
        role_id: '1544083908306403399'
        prompt: >-
          General inquiries, such as how to style CSS, how to use MediaWiki, questions
          about how the farm is ran, or anything that doesn't fit in a particular category
          but may need to be reviewed.

      - key: safety
        name: Trust & Safety
        role_id: '1300548239325401088'
        prompt: >-
          Avoid routing here heavily. You should only route here for T&S policy questions.
          Generally T&S reports are handled through on-wiki reporting tools, not posted
          in the public support forum. Therefore it should only be for policy questions,
          and rarely used as the volume of those is very low.
    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    categories:
      - key: technical
        emoji: '🛠️'
        name: Technical Support
        teams: [tech,support]
        prompt: >-
          A general technical matter. An example of this could be what does x extension do,
          or what does this button do. This is a broad category intended to catch the bulk
          of technical requests.

      - key: styling
        emoji: '🎨'
        name: Styling (CSS/JS)
        teams: [support]
        prompt: >-
          General issues about how to style a wiki, such as "how do I make x", or how do I
          format x. This may also relate to how to use CSS/JS, issues arising from them
          and just general styling.

      - key: account
        emoji: '🔑'
        name: Account
        teams: [stewards]
        prompt: >-
          Anything about getting into an account or changing one, e.g lost
          password, lost 2FA, rename requests, email changes.

      - key: bug
        emoji: '🐛'
        name: Bug
        teams: [tech]
        prompt: >-
          A (reproducible) software fault: something in MediaWiki, an extension
          or a WikiOasis product behaves incorrectly and the reporter can describe
          how to trigger it.
        redirect:
          enabled: true
          url: https://phorge.wikioasis.org/maniphest/task/edit/form/2/
          title: This looks like a bug report
          message: >-
            Thank you for reaching out.

            This appears to be a software bug based on our automated review.
            Please file this issue on Phorge to ensure it is properly tracked
            to a fix. Include the wiki, steps to reproduce and other information
            on the Phorge task form.

            This thread will stay open for follow-ups and mitigation questions
            that you may have for us.
          button_label: File it on Phorge
          colour: '#f5a623'
          once: true
          set_waiting_on_user: true

      - key: question
        emoji: '❓'
        name: Question
        teams: [support]
        prompt: >-
          General support inquiries, basically anything that doesn't fit another
          category.

    # ------------------------------------------------------------------
    # Priorities
    # ------------------------------------------------------------------
    priorities:
      - key: urgent
        name: Urgent
        emoji: '🔴'
        colour: '#e5484d'
        order: 0
        prompt: >-
          The farm or a whole wiki is down or unusable.
          This should not be used lightly, only for the most serious
          of cases needing a near-immediate response.

      - key: high
        name: High
        emoji: '🟠'
        colour: '#f5a623'
        order: 1
        prompt: >-
          A major issue affecting a single user or wiki. This is not necessarily
          an outage, but someone's experience is severely degraded and they are
          needing support for it.

      - key: normal
        name: Normal
        emoji: '🟡'
        colour: '#f2d600'
        order: 2
        prompt: >-
          The default. A real problem or a legitimate request.

      - key: low
        name: Low
        emoji: '🟢'
        colour: '#3ba55d'
        order: 3
        prompt: >-
          Cosmetic issues, questions with no urgency, nice-to-have requests,
          and anything the reporter has already worked around and is only
          mentioning for future use.

    # ------------------------------------------------------------------
    # Statuses
    # ------------------------------------------------------------------
    statuses:
      waiting_on_team:
        label: Waiting on team
        emoji: '🟦'
      waiting_on_user:
        label: Waiting on user
        emoji: '⏳'
      resolved:
        label: Resolved
        emoji: '✅'
    # ------------------------------------------------------------------
    # General Behaviour
    # ------------------------------------------------------------------
    prompt:
      preamble: >-
        You triage threads in the WikiOasis discord support forum. WikiOasis
        is a free wiki farm running MediaWiki; the people writing in are wiki
        administrators and editors, mostly non-technical, and they are usually
        describing a symptom rather than a cause. Be precise and conservative,
        and never invent detail the reporter did not give you. Quite often
        requests are simply queries, which simply need categorising and waiting
        for someone to respond.
      extra: >-
        Treat frustration as an impact, not as a priority signal. Priority comes
        from objective impact, not subjective belief of the impact.

        This question could be the most important thing in the world for the
        person who is reporting it, however it must be taken in moderation.

        If someone reports several unrelated problems in one thread, classify the
        most severe one and let the summary mention that there are others. If a thread
        appears to not be a support request, you can close it as resolved, however you
        cannot do this unless it is clearly trolling, as this can undermine trust from
        users.

    # ------------------------------------------------------------------
    # Metadata/Hardcoded Behaviour
    # ------------------------------------------------------------------
    model: gpt-5.6-luna
    effort: low
    max_categories: 3
    manage_tags: true

    resolution:
      enabled: true
      min_confidence: 0.8
      prefilter: false
      archive: false

    known_issues:
      enabled: true
      min_confidence: 0.75
      title: This may be a known issue
      message: >-
        Thanks for reporting this. We have automatically detected that this is
        most likely an issue we already know about it and it's being worked on.
        There is nothing you need to do; this thread will be updated when it is
        fixed.
      colour: '#5865f2'
      notify_on_resolve: true
      resolved_message: >-
        The issue this thread is discussing should now be resolved by our team.
        Please check whether things are now working as expected, and feel free
        to reply here if you still need help.
      set_waiting_on_user: true

    rescan:
      enabled: true
      min_new_messages: 1
      cooldown_minutes: 10
      context_messages: 25
      updates:
        - categories
        - priority
        - teams
      override_manual: false
      announce_changes: false

    reconcile:
      on_start: true
      interval_minutes: 60
      backfill: true
      backfill_limit: 25

    board:
      debounce_ms: 4000
      refresh_minutes: 15
      max_threads: 200
