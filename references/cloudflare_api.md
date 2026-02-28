# Deploy Reference — Cloudflare, Webflow, Framer

Samvida supports three deployment providers. Each serves `yourdomain.com/llms.txt` in a different way.

---

## Provider Comparison

| Provider | Automation | How it works | Best for |
|---|---|---|---|
| **Cloudflare Workers** | Fully automated | Edge Worker intercepts `/llms.txt` and serves `text/plain` directly | Any site with Cloudflare DNS proxying enabled |
| **Webflow** | Fully automated | Uploads to Webflow CDN, adds 301 redirect from `/llms.txt` → CDN URL | Webflow-hosted sites |
| **Framer** | Semi-automated | Hosts file on GitHub Gist, guides user to add redirect in Framer dashboard | Framer-hosted sites |

---

## Cloudflare Workers

**How to get credentials:**
1. **API Token** — Cloudflare dashboard → My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template → give it permission to: `Workers Scripts: Edit`, `Workers Routes: Edit`
2. **Account ID** — Cloudflare dashboard → top-right corner under your account name
3. **Zone ID** — Cloudflare dashboard → click your domain → right sidebar under "API"

**Requirement:** Your domain's DNS must be proxied through Cloudflare (orange cloud icon ☁️). If it's grey (DNS only), the Worker won't intercept requests.

**What it deploys:**
- A Cloudflare Worker script named `samvida-{domain-slug}`
- A route: `{domain}/llms.txt` → that Worker
- The Worker serves `text/plain; charset=utf-8` with full CORS headers

**CLI:**
```bash
python3 deploy.py \
  --provider cloudflare \
  --llms-txt /tmp/samvida_llms.txt \
  --cf-token YOUR_CF_TOKEN \
  --account-id YOUR_ACCOUNT_ID \
  --zone-id YOUR_ZONE_ID \
  --domain example.com
```

---

## Webflow

**How to get credentials:**
1. **Webflow Site API Token** — Webflow dashboard → your site → Site Settings → Integrations → API Access → Generate API Token
   - Scopes needed: `Assets: Read & Write`, `Sites: Read`, `Pages: Read & Write`, `Publishing: Publish`
2. **Site ID** (optional) — visible in Webflow dashboard URL: `webflow.com/dashboard/sites/{SITE_ID}/...`
   - If omitted, Samvida auto-detects it by matching your domain

**What it deploys:**
1. Uploads `llms.txt` to Webflow's CDN via the Assets API (`POST /v2/sites/{siteId}/assets`)
2. Creates or updates a 301 redirect: `/llms.txt` → CDN URL (`POST /v2/sites/{siteId}/redirects`)
3. Publishes the site (`POST /v2/sites/{siteId}/publish`)

**How it serves:**
- `yourdomain.com/llms.txt` → 301 → `https://uploads-ssl.webflow.com/{siteId}/{hash}/llms.txt`
- Agents follow the redirect automatically. The CDN serves `text/plain` correctly.

**Webflow plan note:** The Redirects API requires Webflow's **Basic plan or above**. If your account is on the free Starter plan, Samvida will output manual redirect instructions.

**CLI:**
```bash
python3 deploy.py \
  --provider webflow \
  --llms-txt /tmp/samvida_llms.txt \
  --webflow-token YOUR_SITE_TOKEN \
  --domain example.com
  # --site-id SITE_ID  (optional — auto-detected)
```

**Key API endpoints used:**
- `GET /v2/sites` — list sites, find by domain
- `POST /v2/sites/{siteId}/assets` — request pre-signed S3 upload URL
- `GET /v2/sites/{siteId}/redirects` — list existing redirects
- `POST /v2/sites/{siteId}/redirects` — create redirect
- `PATCH /v2/sites/{siteId}/redirects/{redirectId}` — update existing redirect
- `POST /v2/sites/{siteId}/publish` — publish to live

---

## Framer

**Why semi-automated:** Framer does not have a public REST API for site hosting, file management, or redirect rules. Their developer APIs are limited to editor plugins and the CMS. There is no endpoint to programmatically upload files or manage redirects.

**What Samvida does:**
1. Uploads `llms.txt` to a GitHub Gist (stable, public, free hosting)
2. Outputs the raw Gist URL
3. Gives step-by-step instructions to add a redirect in Framer's dashboard

**How to get credentials:**
- **GitHub Token** (optional but recommended) — github.com/settings/tokens → Generate new token → `gist` scope only
- If no token provided, Samvida prints the llms.txt content and instructions to host it manually

**CLI:**
```bash
python3 deploy.py \
  --provider framer \
  --llms-txt /tmp/samvida_llms.txt \
  --domain example.com \
  --github-token YOUR_GITHUB_TOKEN
```

**Manual redirect steps in Framer:**
1. Open Framer project → top-left menu → Site Settings
2. General tab → scroll to "Redirect Rules"
3. Add rule: From `/llms.txt` → To `<gist-raw-url>` → Type: 301
4. Save → Publish

**Alternative:** If your Framer site's DNS goes through Cloudflare (you manage the DNS), use the Cloudflare Workers provider instead for a fully automated zero-redirect deploy.

---

## How agents handle the redirect (Webflow & Framer)

Both Webflow and Framer deploys result in a 301 redirect. This is fine for agents:

- All major HTTP clients follow 301 redirects by default
- The final response is served as `text/plain` from the CDN/Gist
- The `llms.txt` spec doesn't require direct serving — redirects are valid

The only case where a redirect causes issues is if an agent's HTTP client has redirect following disabled — which is uncommon and non-standard behavior.
