import os
import sys
import re
import time
import subprocess
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = os.path.join(PROJECT_ROOT, "cloudflared.exe")

print("=" * 75)
print("  POLARIS: Autonomous Polar Station Energy Management System (SIH26061)")
print("                 OFFICIAL LIVE PROTOTYPE HYPERLINK")
print("=" * 75)
print("\n[1/2] Connecting to Cloudflare Global Edge Network...")

if not os.path.exists(CLOUDFLARED):
    CLOUDFLARED = r"C:\Users\Siddhesh\Desktop\cloudflared.exe"

proc = subprocess.Popen(
    [CLOUDFLARED, "tunnel", "--url", "http://127.0.0.1:8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

public_url = None
start_time = time.time()

while time.time() - start_time < 25:
    line = proc.stdout.readline()
    if not line:
        break
    match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
    if match:
        public_url = match.group(0)
        break

if public_url:
    print("\n" + "#" * 75)
    print("  SUCCESS! YOUR LIVE PROTOTYPE HYPERLINK IS READY:")
    print("  " + public_url)
    print("#" * 75)
    print("\n- Evaluators, judges, and teammates can open this link on ANY device.")
    print("- Full real-time telemetry, WebSockets, Supabase and AI decisions are active.")
    print("- Opening the link in your browser now...")
    print("\n>>> DO NOT CLOSE THIS WINDOW while presenting or testing! <<<\n")
    try:
        webbrowser.open(public_url)
    except Exception:
        pass
else:
    print("\n[!] Could not parse tunnel URL automatically. Cloudflare output:")

# Keep tunnel alive and print incoming activity
try:
    for line in proc.stdout:
        # Filter noise, show connections
        if "HTTP" in line or "error" in line.lower() or "inf" in line.lower():
            if "trycloudflare.com" in line or "registered" in line.lower():
                print(line.strip())
except KeyboardInterrupt:
    print("\nClosing tunnel...")
    proc.terminate()
