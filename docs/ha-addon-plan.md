# HA Add-on Support — Implementation Plan

## Context

HAPass is a standalone Docker app (FastAPI + SQLite) that manages guest WiFi/device access for Home Assistant. Goal: make it installable as a native HA add-on from the same repo, with zero code duplication.

**Research findings:** Single-repo pattern works fine for small projects. The repo root doubles as the add-on directory. The `image:` field in `config.yaml` tells the Supervisor to pull the pre-built GHCR image instead of building locally. A `run.sh` entrypoint bridges HA options (`/data/options.json`) to the env vars the app already reads.

**Testing session (2026-03-14):** Deployed to HA OS at 192.168.1.12 as a local add-on. Addon was discovered and started successfully, but the admin UI failed due to ingress path issues.

---

## Issues Discovered

### 1. Ingress Path Prefix (P0 — blocks all UI)

HA ingress proxies requests under `/api/hassio_ingress/{token}/`, stripping this prefix before forwarding to the addon. The app returns absolute URLs (`/admin/dashboard`, `/static/dist.css`) that the browser resolves against the HA root, not the ingress prefix → 404s.

**Affected locations:**
| File | Absolute URLs |
|------|--------------|
| `main.py` | `RedirectResponse(url="/admin/dashboard")` |
| `base.html` | `/static/dist.css`, `/static/icons/icon-192.png` |
| `admin_dashboard.html` | `const BASE = ''`, 4× `src="/static/..."` |
| `guest_pwa.html` | 3× script srcs, manifest link, 3× `fetch(/g/...)`, `EventSource(/g/...)` |
| `expired.html` | `src="/static/theme.js"` |
| `guest.py` | manifest `start_url`, `scope`, 4× icon paths |
| `sw.js` | hardcoded cached URL list |

### 2. Security Headers Block Ingress (P0)

- `X-Frame-Options: DENY` — HA loads addons in an iframe. This header blocks it entirely.
- `CSP connect-src 'self'` — may block SSE/fetch if the ingress origin differs from `self`.

### 3. Guest Links vs Ingress Auth (P1)

Ingress requires HA authentication. Guest links (`/g/{slug}`) are for unauthenticated visitors. If the addon is only accessible via ingress, guests can't use their links.

**Options:**
- **A:** Add `ports` in `config.yaml` to expose 5880 directly (admin via ingress, guests via direct port)
- **B:** Document that guest links are external-only (shared via standalone Docker URL)

### 4. Template Variable Missing in Some Paths (P0)

`base.html` uses `{{ base_path }}` for static assets. If any route rendering a template doesn't pass `base_path`, Jinja2 renders empty or errors. Every `TemplateResponse` must include it.

### 5. Service Worker Caching (P2)

`sw.js` caches a hardcoded URL list with absolute paths. Behind ingress, these paths are wrong. Options: skip SW registration behind ingress, or make the cache list relative.

### 6. Addon Options Persistence (operational knowledge)

Directly editing `/data/options.json` on disk does NOT persist — the Supervisor overwrites it from its internal state on restart. Options must be set via:
- The HA web UI (Settings → Add-ons → HAPass → Configuration)
- The Supervisor API (from inside the HA Core container):
  ```bash
  docker exec homeassistant bash -c 'curl -s -X POST \
    -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"options\":{...}}" \
    http://supervisor/addons/local_ha-pass/options'
  ```

### 7. Store Discovery Command (operational knowledge)

`ha addons reload` does NOT discover new local addons. Use `ha store reload` instead. The addon appears with slug `local_ha-pass`.

---

## Implementation Steps

### Step 1: Ingress-aware base path

Add middleware + pass `base_path` to all templates.

**main.py:**
- In `security_headers` middleware: read `X-Ingress-Path` header → `request.state.ingress_path` (empty string when standalone)
- Fix root redirect: `RedirectResponse(url=f"{base}/admin/dashboard")`
- Pass `base_path=request.state.ingress_path` in admin dashboard template render

**guest.py:**
- Pass `base_path=request.state.ingress_path` in all `TemplateResponse` calls (guest_pwa, expired)
- Fix manifest: prefix `start_url`, `scope`, icon `src` with `base`

**Templates — prefix all absolute URLs with `{{ base_path }}`:**
- `base.html`: `/static/dist.css`, `/static/icons/icon-192.png`
- `admin_dashboard.html`: `const BASE = '{{ base_path }}'`, all `src="/static/..."`
- `guest_pwa.html`: script srcs, manifest link, add `const BASE = '{{ base_path }}'`, prefix all fetch/EventSource URLs with `${BASE}`
- `expired.html`: script src

### Step 2: Security header adjustments

**main.py middleware:**
- When `request.state.ingress_path` is set:
  - Remove `X-Frame-Options` (HA needs iframe embedding)
  - Adjust CSP: add `frame-ancestors 'self'`
- When standalone: keep existing `X-Frame-Options: DENY`

### Step 3: Service worker

- Skip SW registration when behind ingress (detect via `base_path` in template)
- Or: make `sw.js` use relative URLs instead of absolute

### Step 4: Guest access

- Add to `config.yaml`:
  ```yaml
  ports:
    "5880/tcp": null
  ```
  This exposes port 5880 on a random host port. Admin configures the port in the HA UI. Guest links use `http://<ha-ip>:<port>/g/{slug}` directly (no ingress, no auth).
- Update admin dashboard: guest link URL should use `location.origin` only when not behind ingress. Behind ingress, show the direct port URL or a note.

### Step 5: Addon metadata files

Already scaffolded in worktree `agent-a05de743`. Files at repo root:

| File | Purpose |
|------|---------|
| `repository.yaml` | Declares repo as HA add-on repository |
| `config.yaml` | Add-on manifest (ingress, options schema, image ref) |
| `DOCS.md` | User docs shown in HA UI |
| `translations/en.yaml` | Human-readable option labels |
| `run.sh` | Entrypoint: bridges `/data/options.json` → env vars |

**run.sh** detects add-on mode via `/data/options.json` existence:
- Present → reads options, sets `HA_BASE_URL=http://supervisor/core`, `HA_TOKEN=$SUPERVISOR_TOKEN`
- Absent → standalone mode, env vars expected externally

**Dockerfile** change: `COPY run.sh .` + `CMD ["sh", "/app/run.sh"]`

### Step 6: CI/CD updates

- Existing workflow already builds multi-arch and pushes to `ghcr.io/antwertinger/ha-pass`
- `config.yaml` `image:` field references this image
- Version strategy: `config.yaml` `version:` must match the image tag. Update on release.

### Step 7: Testing checklist

- [ ] `docker build && docker run` with env vars still works (standalone)
- [ ] `run.sh` correctly bridges options.json → env vars (simulated add-on mode)
- [ ] `ha store reload` discovers the addon
- [ ] Addon installs and starts
- [ ] Admin dashboard loads via HA sidebar (ingress)
- [ ] Static assets (CSS, JS, fonts, icons) load correctly via ingress
- [ ] Admin login/logout works
- [ ] Token CRUD works
- [ ] Entity picker loads HA entities
- [ ] SSE real-time updates work through ingress
- [ ] Guest link opens via direct port (not ingress)
- [ ] Guest PWA works: state, commands, SSE stream
- [ ] Service worker doesn't break ingress mode
- [ ] Addon restart preserves options and database

---

## File Change Summary

| File | Changes |
|------|---------|
| `main.py` | Middleware: ingress_path. Conditional X-Frame-Options. base_path in template context. Fix redirect. |
| `app/routers/guest.py` | base_path in all template renders. Ingress-aware manifest URLs. |
| `templates/base.html` | `{{ base_path }}` prefix on static assets |
| `templates/admin_dashboard.html` | `BASE = '{{ base_path }}'`, prefix script srcs |
| `templates/guest_pwa.html` | `BASE` variable, prefix script srcs/fetch/EventSource |
| `templates/expired.html` | Prefix script src |
| `static/sw.js` | Skip or use relative URLs behind ingress |
| `Dockerfile` | `COPY run.sh`, change CMD |
| `run.sh` | **New** — options bridge entrypoint |
| `repository.yaml` | **New** — addon repo manifest |
| `config.yaml` | **New** — addon config (note: name conflicts with nothing in project) |
| `DOCS.md` | **New** — addon user docs |
| `translations/en.yaml` | **New** — option labels |
