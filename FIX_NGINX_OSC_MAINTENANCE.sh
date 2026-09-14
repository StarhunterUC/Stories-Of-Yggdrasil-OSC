#!/usr/bin/env bash
set -Eeuo pipefail

CFG="/etc/nginx/sites-available/sam-admin"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${CFG}.before_osc_api_maintenance_fix_${STAMP}"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "[FAIL] Run this script as root on the Sam.py VPS."
  exit 1
fi

if [[ ! -f "$CFG" ]]; then
  echo "[FAIL] Missing $CFG"
  exit 1
fi

cp -a "$CFG" "$BACKUP"
echo "Backup: $BACKUP"

python3 - "$CFG" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "location ^~ /api/osc" in text:
    print("[OK] Dedicated /api/osc location already exists; no insertion needed.")
    raise SystemExit(0)

needle = "    location / {\n"
pos = text.find(needle)
if pos < 0:
    raise SystemExit("[FAIL] Could not find the Admin HTTPS `location / {` block.")

block = '''    # Machine-to-machine OSC API: never redirect JSON clients to HTML maintenance.\n    location ^~ /api/osc {\n        proxy_pass http://127.0.0.1:8765;\n        proxy_http_version 1.1;\n\n        proxy_intercept_errors off;\n\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n        proxy_set_header X-Forwarded-Proto $scheme;\n\n        proxy_connect_timeout 5s;\n        proxy_read_timeout 75s;\n        proxy_send_timeout 75s;\n    }\n\n'''

path.write_text(text[:pos] + block + text[pos:], encoding="utf-8")
print("[OK] Added dedicated /api/osc proxy location.")
PY

if nginx -t; then
  systemctl reload nginx
  echo "[OK] Nginx syntax passed and configuration reloaded."
  echo "OSC API now bypasses the browser maintenance redirect."
else
  echo "[FAIL] nginx -t failed; restoring backup."
  cp -a "$BACKUP" "$CFG"
  nginx -t || true
  exit 1
fi
