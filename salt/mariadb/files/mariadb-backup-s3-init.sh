#!/bin/bash
# Applies the bucket lifecycle policy that tiers MariaDB backups into OVHcloud's
# Infrequent Access class and expires them. Run by Salt on highstate.
#
#   mariadb-backup-s3-init.sh           apply /etc/mariadb-backup/lifecycle.json
#   mariadb-backup-s3-init.sh --check   exit 0 if the live policy already matches
#
# The --check mode is what keeps the Salt state idempotent, and it compares
# semantics rather than bytes: the server echoes the policy back with its own
# field ordering and fills in defaults we never sent, so a literal diff would
# report a change on every single run.
set -euo pipefail

set -a
. /etc/mariadb-backup/s3.env
set +a

LIFECYCLE=/etc/mariadb-backup/lifecycle.json

aws_s3() { aws --endpoint-url "$S3_ENDPOINT" --region "$S3_REGION" "$@"; }

# Reduce a policy to the fields we actually manage, in a stable order.
normalise() {
    jq -S '[.Rules[] | {
        ID,
        Status,
        Prefix: (.Filter.Prefix // .Prefix // ""),
        Transitions: ((.Transitions // []) | map({Days, StorageClass}) | sort_by(.Days)),
        ExpirationDays: (.Expiration.Days // null),
        NoncurrentDays: (.NoncurrentVersionExpiration.NoncurrentDays // null),
        AbortDays: (.AbortIncompleteMultipartUpload.DaysAfterInitiation // null)
    }] | sort_by(.ID)'
}

live_policy() {
    aws_s3 s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET" 2>/dev/null
}

if [ "${1:-}" = "--check" ]; then
    # No policy at all (or an unreachable bucket) leaves live empty, which never
    # matches — so the apply path runs and reports the real error.
    live=$(live_policy | normalise 2>/dev/null) || live=""
    want=$(normalise < "$LIFECYCLE")
    # NoncurrentVersionExpiration only means anything on a versioned bucket, and
    # this one is documented as unversioned — the endpoint is free to drop it
    # from the read-back. If it comes back absent everywhere, neutralise it on
    # the desired side too, otherwise --check would compare null against a real
    # number and report drift on every single highstate, forever. A bucket that
    # DOES echo the field back is still compared strictly.
    if [ -n "$live" ] && [ "$(printf '%s' "$live" | jq -c '[.[].NoncurrentDays] | unique')" = "[null]" ]; then
        want=$(printf '%s' "$want" | jq -S '[.[] | .NoncurrentDays = null]')
    fi
    if [ -n "$live" ] && [ "$live" = "$want" ]; then
        exit 0
    fi
    exit 1
fi

if ! err=$(aws_s3 s3api head-bucket --bucket "$S3_BUCKET" 2>&1); then
    # Pass the CLI's own message through. "Could not connect to the endpoint
    # URL", a 403 and a 404 all land here and each needs a different fix, so
    # swallowing it just sends whoever is reading down the wrong path.
    echo "ERROR: bucket '${S3_BUCKET}' is not reachable at ${S3_ENDPOINT}." >&2
    echo "       aws said: ${err}" >&2
    echo "       Check, in order:" >&2
    echo "         - the endpoint resolves. OVHcloud US regions (us-*) are on" >&2
    echo "           .io.cloud.ovh.us; EU/CA/APAC regions are on .io.cloud.ovh.net." >&2
    echo "         - the bucket exists in region '${S3_REGION}'." >&2
    echo "         - mariadb:backup:s3 access_key/secret_key are valid and the" >&2
    echo "           S3 user has access to this bucket." >&2
    exit 1
fi

aws_s3 s3api put-bucket-lifecycle-configuration \
    --bucket "$S3_BUCKET" \
    --lifecycle-configuration "file://$LIFECYCLE"

# The put above is the part that matters; this read-back is only for the log.
# Under `set -o pipefail` a transient read failure here would exit non-zero and
# have Salt report the state as failed even though the policy was applied.
echo "Applied lifecycle policy to s3://${S3_BUCKET} (${S3_ENDPOINT}):"
live_policy | jq . || echo "  (applied, but reading it back failed)"
