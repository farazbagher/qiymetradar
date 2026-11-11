#!/usr/bin/env python3
"""n8n-i hazırla (python3.9+): Anthropic credential-ı (.env-dən) + workflow-lar + aktivləşdirmə.
İlk işə düşmədə server miqrasiya edərkən CLI işlətmək bazanı pozur, ona görə /healthz gözlənilir."""

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACTIVATE = ["QrErrorNotify", "QrRadarChat"]       # QR1 və QR2 əl ilə işə salınır (Manual Trigger); QR1-in Schedule-ı da var, aşağıya bax


def env():
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def n8n(args, stdin=None):
    return subprocess.run(["docker", "compose", "exec", "-T", "n8n", "sh", "-c", args], cwd=ROOT, input=stdin, capture_output=True, text=True)


def main():
    e = env()
    if not e.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY .env-də boşdur", file=sys.stderr)
        return 1
    for _ in range(60):
        if subprocess.run(["curl", "-sf", "http://localhost:5684/healthz"], capture_output=True).returncode == 0:
            break
        time.sleep(2)
    else:
        print("n8n 2 dəqiqədə qalxmadı", file=sys.stderr)
        return 1
    creds = [{"id": "qrAnthropic00001", "name": "Anthropic account", "type": "anthropicApi",
              "data": {"apiKey": e["ANTHROPIC_API_KEY"], "url": "https://api.anthropic.com", "header": False}}]
    r = n8n("cat > /tmp/qr-creds.json && n8n import:credentials --input=/tmp/qr-creds.json; rm -f /tmp/qr-creds.json", stdin=json.dumps(creds))
    out = (r.stdout + r.stderr).strip()
    print("credential:", out.splitlines()[-1] if out else "?")
    for path in sorted((ROOT / "n8n" / "workflows").glob("qr*.json")):
        r = n8n(f"n8n import:workflow --input=/workflows/{path.name}")
        ok = "Successfully" in r.stdout
        print(("OK   " if ok else "XƏTA ") + path.name)
        if not ok:
            print("   ", (r.stdout + r.stderr).strip()[-300:])
    for wid in ACTIVATE:
        r = n8n(f"n8n publish:workflow --id={wid}")
        out = (r.stdout + r.stderr).strip()
        print("aktiv:", wid, "|", out.splitlines()[0][:100] if out else "")
    subprocess.run(["docker", "compose", "restart", "n8n"], cwd=ROOT, capture_output=True)
    print("n8n restart olundu. UI: http://localhost:5684  (ilk dəfə owner hesabını özün yarat)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
