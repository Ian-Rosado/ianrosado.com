/**
 * import-sabbatical-photos.js
 *
 * Compresses and imports user-selected photos into public/images/sabbatical/
 *
 * Usage:
 *   node scripts/import-sabbatical-photos.js <source-dir>
 *
 * <source-dir> should contain one subfolder per sabbatical slug, e.g.:
 *   my-photos/
 *     days-1-3-wallowas/
 *       IMG_1234.jpg
 *       IMG_1235.HEIC
 *     days-4-5-joseph/
 *       IMG_2001.jpg
 *
 * Output goes to:
 *   public/images/sabbatical/<slug>/photo-01.jpg
 *   public/images/sabbatical/<slug>/photo-02.jpg
 *   ...
 *
 * Photos are:
 *   - Resized to max 1200px on the longest side (preserving aspect ratio)
 *   - Saved as JPEG at 82% quality (~200–400 KB each)
 *   - Sorted alphabetically within each slug folder (preserves iPhone IMG_XXXX order)
 *   - Skipped if destination already exists
 *
 * Supported input formats: JPG, JPEG, PNG, WebP, HEIC (via sharp)
 */

import { readdir, mkdir } from 'fs/promises';
import { join, extname, basename } from 'path';
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

async function processSlug(slug, slugSourceDir) {
  const files = (await readdir(slugSourceDir))
    .filter(f => SUPPORTED.test(f))
    .sort(); // alphabetical = iPhone IMG_XXXX order

  if (files.length === 0) {
    console.log(`  [${slug}] no supported images found, skipping`);
    return;
  }

  const slugDestDir = join(destRoot, slug);
  await mkdir(slugDestDir, { recursive: true });

  let count = 0;
  for (let i = 0; i < files.length; i++) {
    const num = String(i + 1).padStart(2, '0');
    const destFile = join(slugDestDir, `photo-${num}.jpg`);
    const srcFile = join(slugSourceDir, files[i]);

    // Skip if already processed
    try {
      await import('fs/promises').then(m => m.access(destFile));
      console.log(`  [${slug}] photo-${num}.jpg already exists, skipping`);
      continue;
    } catch {
      // doesn't exist, proceed
    }

    try {
      await sharp(srcFile)
        .resize(MAX_PX, MAX_PX, { fit: 'inside', withoutEnlargement: true })
        .jpeg({ quality: QUALITY, mozjpeg: true })
        .toFile(destFile);
      console.log(`  [${slug}] ${files[i]} → photo-${num}.jpg`);
      count++;
    } catch (err) {
      console.error(`  [${slug}] ERROR processing ${files[i]}: ${err.message}`);
    }
  }
  console.log(`  [${slug}] done — ${count} new photo(s) imported`);
}

async function main() {
  const slugDirs = (await readdir(sourceRoot, { withFileTypes: true }))
    .filter(d => d.isDirectory())
    .map(d => d.name);

  if (slugDirs.length === 0) {
    console.log('No subdirectories found in source dir. Nothing to import.');
    return;
  }

  console.log(`Found ${slugDirs.length} slug folder(s) in ${sourceRoot}\n`);

  for (const slug of slugDirs) {
    const slugSourceDir = join(sourceRoot, slug);
    console.log(`Processing: ${slug}`);
    await processSlug(slug, slugSourceDir);
    console.log('');
  }

  console.log('✓ Import complete.');
  console.log(`Photos are in: public/images/sabbatical/`);
  console.log('');
  console.log('Next steps:');
  console.log('  1. Update each .md frontmatter with: photoSource: "sabbatical"');
  console.log('     (this is now the default, so you can just omit photoSource entirely)');
  console.log('  2. Optionally set: layout: "gallery" | "inline" | "carousel"');
  console.log('  3. git add public/images/sabbatical/ && git commit');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
