/**
 * download-sabbatical-photos.js
 *
 * Fetches every sabbatical sub-page from the live Google Sites site,
 * extracts image URLs, and downloads them to:
 *   public/images/sabbatical-from-site/<slug>/photo-01.jpg  ...
 *
 * This folder is intentionally separate from public/images/sabbatical/
 * which will eventually hold the original high-res iPhone photos.
 *
 * Usage:
 *   node scripts/download-sabbatical-photos.js
 *   node scripts/download-sabbatical-photos.js day-7-bryce-canyon   # one slug only
 */

import { mkdir, stat, writeFile } from 'fs/promises';
import { join } from 'path';

const BASE_URL = 'https://www.ianrosado.com/my-life/sabbatical-road-trip/';
const DEST_DIR = 'public/images/sabbatical-from-site';
const HI_RES   = 'w2000';   // replace =wNNNN in Google CDN URLs with this

// Known site-chrome image token (nav/profile photo) — skip on every page
const UI_TOKEN = 'AA5AbUBVQaFRRDzURREpCD-M90f1tPIWU';

const SLUGS = [
  'days-1-3-wallowas',
  'day-4-john-day-and-malheur-wr',
  'day-5-steens-mountain-and-the-alvord-desert',
  'day-6-salt-flats',
  'day-7-bryce-canyon',
  'day-8-capitol-reef',
  'day-9-11-zion',
  'day-12-monument-valley',
  'day-13-mesa-verde',
  'day-14-18-albuquerque',
  'day-19-27-austin-and-dallas',
  'day-28-carlsbad',
  'day-29-31-albuquerque',
  'day-32-santa-fe',
  'day-33-34-drive-to-yosemite',
  'day-35-half-dome',
  'day-36-37-san-jose',
  'day-38-redwoods',
  'day-39-40-sw-oregon-coast',
  'by-the-numbers',
];

// ── helpers ──────────────────────────────────────────────────────────────────

function pad(n) { return String(n).padStart(2, '0'); }

async function extractImageUrls(slug) {
  const res = await fetch(BASE_URL + slug);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${slug}`);
  const html = await res.text();

  // Parse img src attributes from raw HTML (no DOM available in Node)
  const re = /(?:src|href)="(https:\/\/lh3\.googleusercontent\.com\/sitesv\/[^"]+)"/g;
  const seen = new Set();
  let m;
  while ((m = re.exec(html)) !== null) {
    seen.add(m[1]);
  }

  return [...seen]
    .filter(u => !u.includes(UI_TOKEN))              // skip nav/profile image
    .map(u => u.replace(/=w\d+$/, `=${HI_RES}`));    // bump to hi-res
}

async function downloadImage(url, destPath) {
  // Skip if already downloaded
  try { await stat(destPath); return 'skipped'; } catch {}

  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buffer = Buffer.from(await res.arrayBuffer());
  await writeFile(destPath, buffer);
  return 'downloaded';
}

// ── main ─────────────────────────────────────────────────────────────────────

async function processSlug(slug) {
  console.log(`\n── ${slug}`);
  const dir = join(DEST_DIR, slug);
  await mkdir(dir, { recursive: true });

  let urls;
  try {
    urls = await extractImageUrls(slug);
  } catch (err) {
    console.log(`  ⚠️  Could not fetch page: ${err.message}`);
    return { downloaded: 0, skipped: 0, failed: 1 };
  }

  if (urls.length === 0) {
    console.log('  — no content images found');
    return { downloaded: 0, skipped: 0, failed: 0 };
  }

  let downloaded = 0, skipped = 0, failed = 0;

  for (let i = 0; i < urls.length; i++) {
    const filename = `photo-${pad(i + 1)}.jpg`;
    const destPath = join(dir, filename);
    try {
      const result = await downloadImage(urls[i], destPath);
      if (result === 'skipped') {
        console.log(`  ⏭  ${filename} (exists)`);
        skipped++;
      } else {
        console.log(`  ✅ ${filename}`);
        downloaded++;
      }
    } catch (err) {
      console.log(`  ⚠️  ${filename} — ${err.message}`);
      failed++;
    }
  }

  return { downloaded, skipped, failed };
}

async function main() {
  const targetSlug = process.argv[2];
  const slugs = targetSlug ? [targetSlug] : SLUGS;

  if (targetSlug && !SLUGS.includes(targetSlug)) {
    console.error(`❌ Unknown slug: "${targetSlug}"`);
    console.error(`   Valid slugs:\n   ${SLUGS.join('\n   ')}`);
    process.exit(1);
  }

  console.log(`Downloading sabbatical photos → ${DEST_DIR}/`);
  console.log(`Slugs to process: ${slugs.length}`);

  let totalDl = 0, totalSkip = 0, totalFail = 0;

  for (const slug of slugs) {
    const { downloaded, skipped, failed } = await processSlug(slug);
    totalDl   += downloaded;
    totalSkip += skipped;
    totalFail += failed;
  }

  console.log(`\n${'─'.repeat(50)}`);
  console.log(`Done!  ${totalDl} downloaded, ${totalSkip} skipped, ${totalFail} failed.`);
  console.log(`\nPhotos saved to: ${DEST_DIR}/`);
  console.log('These are the old-site versions. Original iPhone photos go in public/images/sabbatical/');
}

main().catch(err => {
  console.error('❌ Fatal:', err.message);
  process.exit(1);
});
