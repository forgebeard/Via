#!/usr/bin/env sh
set -eu

OUT_FILE="${1:-master_key.txt}"
openssl rand -base64 32 | tr -d '\n' | cut -c1-32 > "$OUT_FILE"
chmod 600 "$OUT_FILE"
echo "Master key saved to $OUT_FILE (32 bytes)."
echo "Create docker secret manually (Swarm): docker secret create app_master_key $OUT_FILE"
