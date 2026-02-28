# Cloudflare API Reference

## What we need from the user

1. **API Token** — Cloudflare dashboard → My Profile → API Tokens → Create Token → use "Edit Cloudflare Workers" template
   - Permissions needed: `Workers Scripts: Edit`, `Workers Routes: Edit`
2. **Account ID** — Cloudflare dashboard → top-right of any page after login
3. **Zone ID** — Cloudflare dashboard → click your domain → right sidebar under "API"

---

## API Call 1 — Upload Worker Script

```
PUT https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}
Authorization: Bearer {cf_token}
Content-Type: multipart/form-data
```

Form parts:
- `metadata` (application/json): `{ "main_module": "worker.js", "compatibility_date": "2024-01-01" }`
- `worker.js` (application/javascript+module): the worker script

**Script name convention:** `samvida-{domain-slug}` e.g. `samvida-utkrusht-ai`

**Success:** HTTP 200, `result.id` = script name

**Worker JS template:**
```javascript
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/llms.txt') {
      return new Response(LLMS_TXT_CONTENT, {
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'public, max-age=3600',
          'Access-Control-Allow-Origin': '*'
        }
      });
    }
    return fetch(request);
  }
}

const LLMS_TXT_CONTENT = `LLMS_TXT_PLACEHOLDER`;
```

Note: replace `LLMS_TXT_PLACEHOLDER` with content, escaping backticks as `\`` and `${` as `\${`.

---

## API Call 2 — Add Worker Route

```
POST https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes
Authorization: Bearer {cf_token}
Content-Type: application/json

{ "pattern": "{domain}/llms.txt", "script": "samvida-{domain-slug}" }
```

**Success:** HTTP 200

**Conflict (route already exists):** HTTP 409 — list existing routes and update the matching one:
```
GET https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes
```
Find route where `pattern == "{domain}/llms.txt"`, then:
```
PUT https://api.cloudflare.com/client/v4/zones/{zone_id}/workers/routes/{route_id}
{ "pattern": "{domain}/llms.txt", "script": "samvida-{domain-slug}" }
```

---

## API Call 3 — Verify Live

```bash
curl -s https://{domain}/llms.txt | head -3
```

Retry up to 6 times with 5s delay. Success = HTTP 200 and response starts with `#`.

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| 403 on script upload | Token missing Workers permission | Recreate token with "Edit Cloudflare Workers" template |
| 404 on account | Wrong Account ID | Copy from Cloudflare dashboard top-right |
| 404 on zone | Wrong Zone ID or domain not in this account | Check domain → right sidebar |
| 409 on route | Route already exists | Update existing route (handled automatically) |
| Worker deployed but 404 on verify | DNS propagation delay | Wait 30–60s and retry |
