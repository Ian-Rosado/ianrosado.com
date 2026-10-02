/**
 * vercel-ignore.js
 *
 * Vercel's "Ignored Build Step" (ignoreCommand in vercel.json) for both
 * projects. Exit 0 = skip the build, exit 1 = build.
 *
 * Every deployment counts toward the 10 GB Deployment Storage limit (an
 * ianrosado.com deployment carries ~115 MB of recipe photos/videos), and most
 * commits only touch the Instagram posts or the events pipeline, which
 * neither site serves. So skip the build when a push changes nothing a site
 * is built from.
 *
 * Exception: pdx-events.com production always builds. Its scheduled deploy
 * hook (.github/workflows/rebuild.yml) redeploys the same commit to pull in
 * new Calendar events, and nothing in the build env tells a hook deploy apart
 * from a git push. (ianrosado.com no longer has a scheduled rebuild.)
 */

import { execSync } from 'child_process';

// Paths that don't feed either site's build.
const NON_SITE = [
  /^instagram\//,
  /^\.claude\//,
  /^\.github\//,
  /^scripts\/add-to-calendar\//,
  /^scripts\/event-scrapers\//,
  /^scripts\/logs\//,
  /^scripts\/__pycache__\//,
  /^scripts\/weekly_prep\.cmd$/,
  /^scripts\/google_auth\.py$/,
  /\.md$/,
  /^google_calendar_settings_how_to\.txt$/,
  /^\.gitignore$/,
];

const build = (why) => { console.log(`[vercel-ignore] build: ${why}`); process.exit(1); };
const skip = (why) => { console.log(`[vercel-ignore] skip: ${why}`); process.exit(0); };

if (process.env.BUILD_TARGET === 'pdx-events' && process.env.VERCEL_ENV === 'production') {
  build('pdx-events production (scheduled rebuilds)');
}

// Last successful deployment on this branch; unset for a branch's first deploy,
// in which case fall back to the pushed commit's own changes.
const base = process.env.VERCEL_GIT_PREVIOUS_SHA || 'HEAD~1';

let files;
try {
  files = execSync(`git diff --name-only ${base} HEAD`, { encoding: 'utf8' })
    .split('\n').filter(Boolean);
} catch {
  build(`could not diff against ${base}`);
}

const siteFiles = files.filter((f) => !NON_SITE.some((re) => re.test(f)));
if (siteFiles.length) build(`${siteFiles.length} site file(s) changed since ${base}, e.g. ${siteFiles[0]}`);
skip(`only non-site files changed since ${base} (${files.length})`);
