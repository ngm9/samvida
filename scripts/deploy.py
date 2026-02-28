#!/usr/bin/env python3
"""
deploy.py — Deploy llms.txt as a Cloudflare Worker.

Usage:
    python3 deploy.py \\
        --llms-txt /path/to/llms.txt \\
        --cf-token TOKEN \\
        --account-id ACCOUNT_ID \\
        --zone-id ZONE_ID \\
        --domain example.com

Steps:
    1. Upload Worker script with llms.txt content embedded
    2. Add (or update) a Worker route for domain/llms.txt
    3. Verify the file is live with retries
"""

import sys
import re
import time
import json
import argparse

try:
    import httpx
except ImportError:
    print("Missing dependency. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

CF_API = "https://api.cloudflare.com/client/v4"


def domain_slug(domain: str) -> str:
    """Convert domain to a valid Worker script name slug."""
    return re.sub(r"[^a-z0-9]", "-", domain.lower()).strip("-")


def build_worker_js(llms_txt_content: str) -> str:
    """Embed llms.txt content into the Worker JS template."""
    # Escape backticks and ${ for JS template literal safety
    escaped = llms_txt_content.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    return f"""export default {{
  async fetch(request, env, ctx) {{
    const url = new URL(request.url);
    if (url.pathname === '/llms.txt') {{
      return new Response(LLMS_TXT_CONTENT, {{
        headers: {{
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'public, max-age=3600',
          'Access-Control-Allow-Origin': '*'
        }}
      }});
    }}
    return fetch(request);
  }}
}}

const LLMS_TXT_CONTENT = `{escaped}`;
"""


def upload_worker(client: httpx.Client, account_id: str, script_name: str, worker_js: str) -> None:
    """Upload the Worker script to Cloudflare."""
    url = f"{CF_API}/accounts/{account_id}/workers/scripts/{script_name}"

    files = {
        "metadata": (None, json.dumps({
            "main_module": "worker.js",
            "compatibility_date": "2024-01-01"
        }), "application/json"),
        "worker.js": ("worker.js", worker_js, "application/javascript+module"),
    }

    r = client.put(url, files=files)
    data = r.json()

    if r.status_code == 403:
        print("✖  Permission denied. Your token needs 'Workers Scripts: Edit' permission.")
        print("   Create a new token using the 'Edit Cloudflare Workers' template.")
        sys.exit(1)
    if r.status_code == 404:
        print(f"✖  Account not found. Check your Account ID (got 404 for account '{account_id}').")
        sys.exit(1)
    if not data.get("success"):
        errors = data.get("errors", [])
        print(f"✖  Worker upload failed: {errors}")
        sys.exit(1)

    print(f"  ✓ Worker '{script_name}' uploaded")


def add_or_update_route(client: httpx.Client, zone_id: str, domain: str, script_name: str) -> None:
    """Add a Worker route, or update it if one already exists."""
    pattern = f"{domain}/llms.txt"
    routes_url = f"{CF_API}/zones/{zone_id}/workers/routes"

    # Try to create
    r = client.post(routes_url, json={"pattern": pattern, "script": script_name})
    data = r.json()

    if r.status_code == 404:
        print(f"✖  Zone not found. Check your Zone ID (got 404 for zone '{zone_id}').")
        print("   Find it: Cloudflare dashboard → click your domain → right sidebar under 'API'.")
        sys.exit(1)

    if data.get("success"):
        print(f"  ✓ Route added: {pattern}")
        return

    # Check if it's a conflict (route already exists)
    errors = data.get("errors", [])
    is_conflict = any(e.get("code") in (10020, 10026) or "already" in str(e).lower() for e in errors)

    if is_conflict:
        # Find and update the existing route
        r2 = client.get(routes_url)
        routes = r2.json().get("result", [])
        existing = next((ro for ro in routes if ro.get("pattern") == pattern), None)

        if existing:
            route_id = existing["id"]
            r3 = client.put(f"{routes_url}/{route_id}", json={"pattern": pattern, "script": script_name})
            if r3.json().get("success"):
                print(f"  ✓ Route updated: {pattern}")
                return

    print(f"✖  Route setup failed: {errors}")
    sys.exit(1)


CMS_SIGNATURES = {
    "framer":      {"header": "server", "value": "framer",      "name": "Framer"},
    "webflow":     {"header": "x-wf-",  "value": "",            "name": "Webflow"},
    "squarespace": {"header": "server", "value": "squarespace", "name": "Squarespace"},
    "shopify":     {"header": "server", "value": "shopify",     "name": "Shopify"},
    "ghost":       {"header": "server", "value": "ghost",       "name": "Ghost"},
    "wordpress":   {"header": "x-powered-by", "value": "wordpress", "name": "WordPress"},
}

CMS_INSTRUCTIONS = {
    "Framer": """
  📋 How to update your llms.txt in Framer:
     1. Open your Framer project
     2. Go to Site Settings → General → Custom Code (or Pages → llms.txt if you have a custom page)
     3. If llms.txt is a CMS page: open it, paste the new content, republish
     4. If it's a static file: go to Site Settings → Hosting → Custom Files, upload the new llms.txt
     5. Republish your site
""",
    "Webflow": """
  📋 How to update your llms.txt in Webflow:
     1. Open your Webflow project → Pages
     2. Find the /llms.txt static page (or create one: Add Page → Static Page → path: llms.txt)
     3. Paste the new content into the page body as plain text
     4. Publish the site
     Note: Phase 2 of Samvida will support updating this via the Webflow API automatically.
""",
    "Squarespace": """
  📋 How to update your llms.txt in Squarespace:
     1. Go to Settings → Advanced → Code Injection (for simple text)
     2. Or use Pages → Not Linked → add a page at path /llms.txt
     3. Paste the content and save
""",
    "Shopify": """
  📋 How to update your llms.txt in Shopify:
     1. Online Store → Themes → Edit Code
     2. Under Templates, look for or create llms.txt.liquid
     3. Paste the content and save
""",
    "default": """
  📋 Your site is managed by a CMS that serves /llms.txt directly.
     The Cloudflare Worker can't intercept it without proxying enabled.

     Easiest fix: paste the generated llms.txt content directly into your CMS.
     The file is saved at: /tmp/samvida_llms.txt
""",
}


def detect_cms(headers: dict) -> str | None:
    """Detect CMS from response headers. Returns CMS name or None."""
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
    for cms_id, sig in CMS_SIGNATURES.items():
        h = sig["header"].lower()
        v = sig["value"].lower()
        if h in headers_lower and (not v or v in headers_lower[h]):
            return sig["name"]
        # Webflow uses x-wf-* headers
        if cms_id == "webflow" and any(k.startswith("x-wf-") for k in headers_lower):
            return sig["name"]
    return None


def verify_live(domain: str, retries: int = 8, delay: int = 5):
    """
    Poll until llms.txt is live or retries exhausted.
    Returns (success: bool, cms: str | None)
    """
    url = f"https://{domain}/llms.txt"
    print(f"  ⏳ Verifying {url} ", end="", flush=True)

    last_headers = {}
    for i in range(retries):
        try:
            r = httpx.get(url, timeout=10, follow_redirects=True)
            last_headers = dict(r.headers)
            if r.status_code == 200 and r.text.strip().startswith("#"):
                # Check if it's OUR content or the old CMS content
                # Our content starts with "# {domain}" and was just deployed
                # We detect CMS to warn even on "success" if Worker lost
                cms = detect_cms(last_headers)
                if cms:
                    print()
                    return False, cms
                print(" ✓")
                return True, None
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(delay)

    print()
    cms = detect_cms(last_headers)
    return False, cms


def main():
    parser = argparse.ArgumentParser(description="Deploy llms.txt via Cloudflare Workers")
    parser.add_argument("--llms-txt", required=True, help="Path to llms.txt file")
    parser.add_argument("--cf-token", required=True, help="Cloudflare API token")
    parser.add_argument("--account-id", required=True, help="Cloudflare Account ID")
    parser.add_argument("--zone-id", required=True, help="Cloudflare Zone ID")
    parser.add_argument("--domain", required=True, help="Domain e.g. utkrusht.ai")
    args = parser.parse_args()

    # Read llms.txt
    try:
        llms_txt = open(args.llms_txt).read()
    except FileNotFoundError:
        print(f"✖  File not found: {args.llms_txt}")
        sys.exit(1)

    domain = args.domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    script_name = f"samvida-{domain_slug(domain)}"

    print(f"🚀 Deploying llms.txt to {domain}")
    print(f"   Script name: {script_name}")

    headers = {
        "Authorization": f"Bearer {args.cf_token}",
        "User-Agent": "samvida/0.1.0",
    }

    with httpx.Client(headers=headers, timeout=30) as client:
        # Step 1 — Upload Worker
        worker_js = build_worker_js(llms_txt)
        upload_worker(client, args.account_id, script_name, worker_js)

        # Step 2 — Add/update route
        add_or_update_route(client, args.zone_id, domain, script_name)

    # Step 3 — Verify
    success, cms = verify_live(domain)

    if success:
        print(f"\n✅ Live at https://{domain}/llms.txt")
    elif cms:
        instructions = CMS_INSTRUCTIONS.get(cms, CMS_INSTRUCTIONS["default"])
        print(f"\n⚠️  Your site is hosted on {cms}, which serves /llms.txt directly.")
        print("   The Cloudflare Worker was deployed successfully, but {cms}'s origin is taking priority.")
        print("   This is because your DNS A record points to {cms}'s servers, bypassing Cloudflare's proxy.")
        print()
        print(f"SAMVIDA_CMS:{cms}")  # machine-readable signal for SKILL.md to parse
        print(instructions)
        print(f"  Your generated llms.txt is ready at: /tmp/samvida_llms.txt")
    else:
        print(f"\n⚠️  Deployed but not yet reachable at https://{domain}/llms.txt")
        print("   DNS propagation can take 1–2 minutes.")
        print(f"   Try: curl https://{domain}/llms.txt")


if __name__ == "__main__":
    main()
