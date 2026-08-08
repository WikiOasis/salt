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
    if [ -n "$live" ] && [ "$live" = "$want" ]; then
        exit 0
    fi
    exit 1
fi

if ! aws_s3 s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>&1; then
    echo "ERROR: bucket '${S3_BUCKET}' is not reachable at ${S3_ENDPOINT}." >&2
    echo "       Create it first and check mariadb:backup:s3 credentials/region." >&2
    exit 1
fi

aws_s3 s3api put-bucket-lifecycle-configuration \
    --bucket "$S3_BUCKET" \
    --lifecycle-configuration "file://$LIFECYCLE"

echo "Applied lifecycle policy to s3://${S3_BUCKET} (${S3_ENDPOINT}):"
live_policy | jq .
