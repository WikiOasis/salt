#!/bin/bash
# Verifies the authentik backup bucket is reachable, and optionally applies the
# lifecycle policy. Run by Salt on highstate.
#
#   authentik-backup-s3-init            verify the bucket; apply lifecycle if enabled
#   authentik-backup-s3-init --check    exit 0 if there is nothing to do
#
# Checking the bucket at highstate time is the point of this script: without it
# a wrong endpoint, a mistyped bucket or a revoked key is not discovered until
# 03:30, by a cron job whose output nobody reads.
set -euo pipefail

set -a
. /etc/authentik-backup/s3.env
set +a

LIFECYCLE=/etc/authentik-backup/lifecycle.json

aws_s3() { aws --endpoint-url "$S3_ENDPOINT" --region "$S3_REGION" "$@"; }

# Reduce a policy to the fields we actually manage, in a stable order. The
# server echoes policies back with its own field ordering and fills in defaults
# we never sent, so a literal diff would report a change on every run.
normalise() {
    jq -S '[.Rules[] | {
        ID,
        Status,
        Prefix: (.Filter.Prefix // .Prefix // ""),
        ExpirationDays: (.Expiration.Days // null),
        NoncurrentDays: (.NoncurrentVersionExpiration.NoncurrentDays // null),
        AbortDays: (.AbortIncompleteMultipartUpload.DaysAfterInitiation // null)
    }] | sort_by(.ID)'
}

if [ -z "$S3_BUCKET" ]; then
    # No bucket configured: backups stay local. Not an error — the local dump is
    # still taken — but say so, because "not configured" and "configured and
    # broken" look identical from the outside.
    if [ "${1:-}" = "--check" ]; then exit 0; fi
    echo "authentik:backup:s3:bucket is unset — dumps will be kept locally only."
    exit 0
fi

if [ "${1:-}" = "--check" ]; then
    # Bucket reachability is checked on every apply, never skipped, so --check
    # only ever reports on the lifecycle policy.
    if [ "$S3_MANAGE_LIFECYCLE" != "true" ]; then exit 0; fi
    live=$(aws_s3 s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET" 2>/dev/null | normalise 2>/dev/null) || live=""
    want=$(normalise < "$LIFECYCLE")
    # NoncurrentVersionExpiration only means anything on a versioned bucket, and
    # an unversioned one is free to drop the field from the read-back. If it
    # comes back absent everywhere, neutralise it on the desired side too, or
    # --check compares null against a real number and reports drift forever.
    if [ -n "$live" ] && [ "$(printf '%s' "$live" | jq -c '[.[].NoncurrentDays] | unique')" = "[null]" ]; then
        want=$(printf '%s' "$want" | jq -S '[.[] | .NoncurrentDays = null]')
    fi
    [ -n "$live" ] && [ "$live" = "$want" ] && exit 0
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
    echo "         - authentik:backup:s3 access_key/secret_key are valid and the" >&2
    echo "           S3 user has access to this bucket." >&2
    exit 1
fi
echo "bucket s3://${S3_BUCKET} reachable at ${S3_ENDPOINT}"

if [ "$S3_MANAGE_LIFECYCLE" != "true" ]; then
    echo "manage_lifecycle is false — leaving the bucket's lifecycle policy alone."
    echo "Remote retention is whatever policy already exists on this bucket."
    exit 0
fi

aws_s3 s3api put-bucket-lifecycle-configuration \
    --bucket "$S3_BUCKET" \
    --lifecycle-configuration "file://$LIFECYCLE"

# The put above is the part that matters; this read-back is only for the log, so
# a transient failure here must not exit non-zero and have Salt report the state
# as failed even though the policy was applied.
echo "Applied lifecycle policy to s3://${S3_BUCKET}:"
aws_s3 s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET" | jq . \
    || echo "  (applied, but reading it back failed)"
