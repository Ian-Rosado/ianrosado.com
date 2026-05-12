/**
 * convert-heic.js
 *
 * Converts all .heic / .HEIC files in a directory (recursive) to .jpg.
 * Skips files that already have a matching .jpg alongside them.
 * Uses sharp (libvips) for broad compatibility with all HEIC variants.
 *
 * Usage:
 *   node scripts/convert-heic.js                             # all recipe folders
 *   node scripts/convert-heic.js public/images/recipes/simple-carrot-cake
 *   node scripts/convert-heic.js "C:\Users\you\Downloads\photos"
 */

import sharp from 'sharp';
import { readdir, stat } from 'fs/promises';
import { join, extname, basename, dirname } from 'path';

const DEFAULT_DIR = 'public/images/recipes';
const QUALITY = 90; // 1–100, higher = bigger file / better quality

async function findHeicFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await findHeicFiles(full));
    } else if (extname(entry.name).toLowerCase() === '.heic') {
      files.push(full);
    }
  }
  return files;
}

async function convertFile(heicPath) {
  const jpgPath = join(dirname(heicPath), basename(heicPath, extname(heicPath)) + '.jpg');

  // Skip if JPG already exists
  try {
    await stat(jpgPath);
    console.log(`  ⏭  Skipping (JPG exists): ${basename(heicPath)}`);
    return { status: 'skipped' };
  } catch {
    // doesn't exist — proceed
  }

  try {
    await sharp(heicPath)
      .jpeg({ quality: QUALITY, mozjpeg: true })
      .toFile(jpgPath);
    console.log(`  ✅ Saved:      ${basename(jpgPath)}`);
    return { status: 'converted' };
  } catch (err) {
    console.log(`  ⚠️  Failed:     ${basename(heicPath)} — ${err.message}`);
    return { status: 'failed' };
  }
}

async function main() {
  const targetDir = process.argv[2] ?? DEFAULT_DIR;

  let dirStat;
  try {
    dirStat = await stat(targetDir);
  } catch {
    console.error(`❌ Directory not found: ${targetDir}`);
    process.exit(1);
  }
  if (!dirStat.isDirectory()) {
    console.error(`❌ Not a directory: ${targetDir}`);
    process.exit(1);
  }

  const files = await findHeicFiles(targetDir);
  if (files.length === 0) {
    console.log(`No .heic files found in ${targetDir}`);
    process.exit(0);
  }

  console.log(`\nFound ${files.length} HEIC file(s) in ${targetDir}\n`);

  let converted = 0, skipped = 0, failed = 0;
  for (const file of files) {
    const result = await convertFile(file);
    if (result.status === 'converted') converted++;
    else if (result.status === 'skipped') skipped++;
    else failed++;
  }

  console.log(`\nDone! ${converted} converted, ${skipped} skipped, ${failed} failed.`);
}

main().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});
