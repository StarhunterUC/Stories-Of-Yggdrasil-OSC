$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = "root@199.115.76.249"

scp "$Here\patch_osc_attacker_catalog_v0814.py" "${Server}:/tmp/patch_osc_attacker_catalog_v0814.py"
scp "$Here\verify_osc_attacker_catalog_v0814.py" "${Server}:/tmp/verify_osc_attacker_catalog_v0814.py"

ssh $Server 'cd /opt/sam && PYTHONPATH=/opt/sam /opt/sam/.venv/bin/python /tmp/patch_osc_attacker_catalog_v0814.py --dry-run'
ssh $Server 'cd /opt/sam && PYTHONPATH=/opt/sam /opt/sam/.venv/bin/python /tmp/patch_osc_attacker_catalog_v0814.py --restart'
ssh $Server 'cd /opt/sam && PYTHONPATH=/opt/sam /opt/sam/.venv/bin/python /tmp/verify_osc_attacker_catalog_v0814.py'
ssh $Server 'curl -sS http://127.0.0.1:8765/api/osc/health && echo && systemctl status sam --no-pager -l | head -n 30'
