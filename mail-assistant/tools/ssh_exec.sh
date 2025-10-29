#!/bin/sh
# Simple adapter: read JSON from stdin:
# { "host":"1.2.3.4", "user":"ubuntu", "cmd":"..."}
set -e
python3 - <<'PY'
import sys,json,subprocess
data = json.load(sys.stdin)
host = data.get("host")
user = data.get("user","root")
cmd = data.get("cmd","")
key = data.get("key_path","/app/persistent/keys/agent_key")
ssh_cmd = ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no", f"{user}@{host}", cmd]
proc = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
print(json.dumps(out))
PY