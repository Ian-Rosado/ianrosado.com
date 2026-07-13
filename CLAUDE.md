# ianrosado.com — Claude Context

Personal website for Ian Rosado. Built with Astro v6 + Tailwind v4, deployed on Vercel, domain on GoDaddy.

---

## Tech Stack

- **Framework:** Astro v6 (static site generator)
- **Styling:** Tailwind CSS v4 + `@tailwindcss/typography`
- **Fonts:** Inter (sans) + Lora (serif) via Google Fonts
- **Content:** Astro content collections (markdown files in `src/content/recipes/`)
- **Hosting:** Vercel (`ianrosado-com.vercel.app`) — auto-deploys on push to `main`
- **Domain:** `ianrosado.com` on GoDaddy — DNS not yet pointed at Vercel (still on Google Sites)

---

## Running Locally

```bash
# PATH fix needed on Windows — node isn't in default shell PATH
$env:PATH = "C:\Program Files\nodejs;" + $env:PATH
npm run dev        # → http://localhost:4321
```

The `.claude/launch.json` is configured for the preview server using the full node path.

---

## Portland Events Tooling Setup (new machine)

The Portland Events calendar scripts and Instagram workflows (`scripts/add-to-calendar/`,
`.claude/skills/portland-events-instagram-post/`, `.claude/skills/portland-events-instagram-ingest/`,
`.claude/skills/portland-events-add-workflow/`)
need a few things that **aren't in git** — set these up once per machine:

1. **Copy the calendar credentials** — these are gitignored on purpose (secrets) and must be
   carried over manually (USB, password manager, etc.), not via git:
   - `scripts/add-to-calendar/credentials.json`
   - `scripts/add-to-calendar/token.json`

2. **Install Python deps + Playwright's browser:**
   ```powershell
   pip install google-auth google-api-python-client playwright gspread requests
   pip install yt-dlp   # optional — improves the Instagram-ingest fetch hit rate
   playwright install chromium
   ```

   The Instagram-ingest flow ("save posts on your phone all week, then run the
   batch") is documented in the **portland-events-instagram-ingest** skill and
   driven by `scripts/add-to-calendar/instagram_events.py`. Links land in an
   "IG Inbox" sheet tab; the script fetches each flyer + caption, Claude extracts
   the event fields, and the rows feed the normal add-to-calendar review/commit.

3. **Install GitHub CLI** (so PRs can be opened from the new machine), then authenticate:
   ```powershell
   winget install --id GitHub.cli
   gh auth login
   ```

Once those three are done, the calendar-add and Instagram-post skills work identically to any
other machine — paste event-edit URLs, the skill looks them up, fills the template, renders the
PNG, and you commit/PR as usual.

4. **(Optional, one machine only) Scheduled weekly prep** — the desktop runs
   `scripts/weekly_prep.cmd` via Task Scheduler ("PortlandEvents Weekly Prep",
   Mondays 6:00 AM): scrape → push to Inbox (cleared) → `--stage prep` →
   `--stage review`, so the Review tab is phone-ready with no commands. Logs in
   `scripts/logs/`. After the y/n pass, commit with
   `python portland_events_add.py --stage commit --yes`. Register on a new machine:
   ```powershell
   schtasks /Create /TN "PortlandEvents Weekly Prep" /TR '"<repo>\scripts\weekly_prep.cmd"' /SC WEEKLY /D MON /ST 06:00
   ```

5. **(Optional) Instagram fetch cookies** — export a Netscape `cookies.txt` from a
   browser logged into instagram.com and save it as
   `scripts/add-to-calendar/ig_cookies.txt` (gitignored). The IG-ingest fetch uses
   it automatically; without it, yt-dlp's Chrome-cookie fallback fails on Windows.

---

## Project Structure

```
src/
  content/
    recipes/           ← one .md file per recipe
  content.config.ts    ← Astro v6 content collection schema
  layouts/
    Layout.astro       ← shared layout: nav, footer, per-page background
  pages/
    index.astro
    portland-events.astro
    recipes/
      index.astro      ← recipe grid
      [slug].astro     ← individual recipe template
    more-pdx/
    my-life/
    about.astro
  styles/
    global.css         ← Tailwind imports, font theme, per-page background patterns
```

---

## Design System

- **Accent color:** Orange — `orange-600` (#ea580c) for buttons, active nav, tags, bullet dots
- **Background:** Diagonal gradient white → orange (top-left → bottom-right) defined as `--gradient-base` in `global.css`
- **Per-page patterns** layered over the gradient via body class:
  - `page-home` — gradient only
  - `page-events` — dot grid
  - `page-recipes` — diagonal lines
  - `page-mylife` — horizontal ruled lines
  - `page-about` — gradient only
- **Fonts:** Serif (Lora) for headings/titles, sans (Inter) for body
- Pass `pageClass="page-xxx"` prop to `<Layout>` on each page

---

## Recipe Content Format

Each recipe is a markdown file in `src/content/recipes/`. The frontmatter schema (defined in `src/content.config.ts`):

```yaml
---
title: "Recipe Title"
date: 2024-01-15          # used for sorting, newer = first
description: "One line tagline shown on recipe cards"
coverImage: "/images/recipes/recipe-slug/cover.jpg"   # optional, shows on card + top of recipe
tags: ["tag1", "tag2"]    # shown as orange pills
ingredients:
  - "quantity ingredient"
equipment:
  - "item"
---
```

The markdown body contains step-by-step instructions. Photos are inserted as standard markdown images:

```markdown
![Step description](/images/recipes/recipe-slug/step1.jpg)
```

Or as HTML comments as placeholders (current state):

```markdown
<!-- Photo: description of what goes here -->
```

---

## Photo Migration (PENDING — main outstanding task)

**Status:** All 6 recipes have content and photo placeholders. No actual photos added yet.

**To add photos for a recipe:**

1. Create a folder: `public/images/recipes/<recipe-slug>/`
   - Slugs match the markdown filename without `.md`:
     - `gf-no-bake-chocolate-peanut-butter-cookies`
     - `gooey-oatmeal-chocolate-chip-cookies`
     - `vegan-chocolate-cake`
     - `simple-chocolate-mousse`
     - `simple-carrot-cake`
     - `exquisite-almond-sugar-cookies`

2. Add photos to that folder (JPG/WebP, reasonable size — aim for <500KB each)

3. In the recipe's `.md` file:
   - Replace `<!-- Photo: description -->` comments with `![alt text](/images/recipes/slug/filename.jpg)`
   - Set `coverImage: "/images/recipes/slug/cover.jpg"` in frontmatter (the cover shows on the recipe card grid)

4. Commit and push — Vercel auto-deploys

**Photo sources:** Ian's photos are on Google Photos under `nai1911@gmail.com`. Each recipe has 6–13 process photos taken during cooking.

---

## DNS (PENDING — do after all content is migrated)

The domain still points at Google Sites. To cut over:

1. In GoDaddy DNS, edit the `www` CNAME:
   - Current value: `ghs.googlehosted.com`
   - New value: `ca23b6969de5679d.vercel-dns-017.com`
2. The `A` records for `@` are locked (GoDaddy forwarding service) — leave them, they redirect `ianrosado.com` → `www.ianrosado.com` which is fine
3. After saving, hit **Refresh** in Vercel → Domains — should go green within minutes

---

## Pages Still Needing Content

| Page | Status | Notes |
|------|--------|-------|
| `/recipes/*` | ✅ Content done | Photos pending |
| `/portland-events` | ✅ Done | Trivia night calendar embeds still missing (need URLs from old site) |
| `/more-pdx/favorites` | 🔲 Placeholder | Needs content migrated from Google Sites |
| `/more-pdx/pickup-soccer` | 🔲 Placeholder | Needs content migrated from Google Sites |
| `/my-life/sabbatical` | 🔲 Placeholder | 20+ day entries need migrating from Google Sites |
| `/about` | 🔲 Partial | Needs profile photo at `public/images/ian.jpg` — uncomment the `<img>` tag in `src/pages/about.astro` |

---

## Conventions

- Always branch + PR — no direct commits to main (exception: Ian approved direct commits during initial build)
- Run `git fetch origin && git pull --rebase` before pushing
- Dev server requires Node in PATH — see running locally section above
- Tailwind v4 uses `@import "tailwindcss"` not `@tailwind base/components/utilities`
- Content collections use Astro v6 API: `render(entry)` not `entry.render()`, `entry.id` not `entry.slug`
