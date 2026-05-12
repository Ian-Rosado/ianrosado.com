/**
 * import-sabbatical-photos.js
 *
 * Compresses and imports curated sabbatical photos into public/images/sabbatical/
 *
 * Usage:
 *   node scripts/import-sabbatical-photos.js <source-dir>
 *
 * <source-dir> must contain one subfolder per sabbatical slug, each with an
 * "include" subfolder holding only the photos to include on the site, e.g.:
 *
 *   C:\Users\nai19\Downloads\For_Website\sabbatical\
 *     days-1-3-wallowas\
 *       include\
 *         IMG_4147.JPG
 *         IMG_4148.JPG
 *     day-6-salt-flats\
 *       include\
 *         IMG_5001.JPG
 *
 * Output goes to:
 *   public/images/sabbatical/<slug>/photo-01.jpg
 *   public/images/sabbatical/<slug>/photo-02.jpg
 *   ...
 *
 * Photos are:
 *   - Resized to max 1200px on the longest side (preserving aspect ratio)
 *   - Saved as JPEG at 82% quality (~200–400 KB each)
 *   - Sorted alphabetically (preserves iPhone IMG_XXXX order)
 *   - Skipped if destination already exists
 *
 * Supported input formats: JPG, JPEG, PNG, WebP, HEIC
 */

import { readdir, mkdir, access } from 'fs/promises';
import { join } from 'path';
import sharp from 'sharp';

const SUPPORTED = /\.(jpe?g|png|webp|heic|heif)$/i;
const MAX_PX = 1200;
const QUALITY = 82;

const sourceRoot = process.argv[2];
if (!sourceRoot) {
  console.error('Usage: node scripts/import-sabbatical-photos.js <source-dir>');
  process.exit(1);
}

const destRoot = join(process.cwd(), 'public', 'images', 'sabbatical');

async function fileExists(p) {
  try { await access(p); return true; } catch { return false; }
}

async function processSlug(slug) {
  const includeDir = join(sourceRoot, slug, 'include');

  // Check that include/ folder exists
  const allFiles = await readdir(includeDir).catch(() => null);
  if (allFiles === null) {
    console.log(`  [${slug}] no "include" subfolder found — skipping`);
    return;
  }

  const photos = allFiles.filter(f => SUPPORTED.test(f)).sort();

  if (photos.length === 0) {
    console.log(`  [${slug}] "include" folder is empty — skipping`);
    return;
  }

  console.log(`  [${slug}] ${photos.length} photo(s) to process`);

  const slugDestDir = join(destRoot, slug);
  await mkdir(slugDestDir, { recursive: true });

  let imported = 0;
  let skipped = 0;

  for (let i = 0; i < photos.length; i++) {
    const num = String(i + 1).padStart(2, '0');
    const srcFile = join(includeDir, photos[i]);
    const destFile = join(slugDestDir, `photo-${num}.jpg`);

    if (await fileExists(destFile)) {
      console.log(`    photo-${num}.jpg already exists — skipping`);
      skipped++;
      continue;
    }

    try {
      await sharp(srcFile)
        .resize(MAX_PX, MAX_PX, { fit: 'inside', withoutEnlargement: true })
        .jpeg({ quality: QUALITY, mozjpeg: true })
        .toFile(destFile);
      console.log(`    ${photos[i]} → photo-${num}.jpg`);
      imported++;
    } catch (err) {
      console.error(`    ERROR processing ${photos[i]}: ${err.message}`);
    }
  }

  console.log(`  [${slug}] done — ${imported} imported, ${skipped} already existed`);
}

async function main() {
  const entries = await readdir(sourceRoot, { withFileTypes: true });
  const slugDirs = entries.filter(d => d.isDirectory()).map(d => d.name).sort();

  if (slugDirs.length === 0) {
    console.log('No subdirectories found in source dir. Nothing to import.');
    return;
  }

  console.log(`Found ${slugDirs.length} slug folder(s) in ${sourceRoot}\n`);

  for (const slug of slugDirs) {
    console.log(`Processing: ${slug}`);
    await processSlug(slug);
    console.log('');
  }

  console.log('✓ Import complete. Photos saved to: public/images/sabbatical/');
  console.log('');
  console.log('Next steps:');
  console.log('  1. In each .md frontmatter, remove photoSource: "sabbatical-from-site"');
  console.log('     (the new default is "sabbatical", so omitting it is fine)');
  console.log('  2. Optionally add: layout: "gallery" | "inline" | "carousel"');
  console.log('  3. git add public/images/sabbatical/ && git commit && git push');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
