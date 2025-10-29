#!/bin/sh
set -e

: "${RQ_DASH_USER:?Need RQ_DASH_USER env var}"
: "${RQ_DASH_PASS:?Need RQ_DASH_PASS env var}"

HTPASSWD_FILE=/etc/nginx/.htpasswd

if [ -f "$HTPASSWD_FILE" ]; then
  htpasswd -b "$HTPASSWD_FILE" "$RQ_DASH_USER" "$RQ_DASH_PASS"
else
  htpasswd -b -c "$HTPASSWD_FILE" "$RQ_DASH_USER" "$RQ_DASH_PASS"
fi

exec nginx -g 'daemon off;'