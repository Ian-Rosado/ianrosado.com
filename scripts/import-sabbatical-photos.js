/**
 * import-sabbatical-photos.js
 *
 * Imports curated sabbatical media into public/images/sabbatical/
 *
 * Usage:
 *   node scripts/import-sabbatical-photos.js <source-dir>
 *
 * <source-dir> must contain one subfolder per sabbatical slug, each with an
 * "include" subfolder. Drop any mix of photos, GIFs, and MP4s in there:
 *
 *   sabbatical/
 *     days-1-3-wallowas/
 *       include/
 *         IMG_4147.JPG      ← photo: compressed + renamed photo-01.jpg
 *         IMG_4148.JPG      ← photo: compressed + renamed photo-02.jpg
 *         waterfall.gif     ← GIF: converted to waterfall.mp4
 *         timelapse.mp4     ← MP4: copied as-is
 *
 * Output goes to public/images/sabbatical/<slug>/
 *
 * File handling by type:
 *   Photos (JPG/PNG/WebP/HEIC) → resized to max 1200px, 82% JPEG quality,
 *                                 renamed photo-01.jpg, photo-02.jpg, ...
 *                                 (sorted alphabetically = iPhone IMG_XXXX order)
 *   GIFs                       → converted to MP4 via ffmpeg, same base name
 *                                 e.g. waterfall.gif → waterfall.mp4
 *   MP4s                       → copied as-is, same filename
 *
 * GIFs and MP4s keep their original names so you can reference them
 * in markdown by name:
 *   <video autoplay loop muted playsinline class="w-full rounded-xl my-6">
 *     <source src="/images/sabbatical/days-1-3-wallowas/waterfall.mp4" type="video/mp4">
 *   </video>
 *
 * All files are skipped if the destination already exists.
 */

import { readdir, mkdir, access, copyFile } from 'fs/promises';
import { join, basename, extname } from 'path';
import { spawn } from 'child_process';
import sharp from 'sharp';
import ffmpegPath from 'ffmpeg-static';

const PHOTO_EXT  = /\.(jpe?g|png|webp|heic|heif)$/i;
const GIF_EXT    = /\.gif$/i;
const MP4_EXT    = /\.mp4$/i;

const MAX_PX  = 1200;
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

function ffmpegConvert(src, dest) {
  return new Promise((resolve, reject) => {
    const args = [
      '-y',                          // overwrite without asking
      '-i', src,
      '-movflags', 'faststart',
      '-pix_fmt', 'yuv420p',
      '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
      dest,
    ];
    const proc = spawn(ffmpegPath, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    let errOut = '';
    proc.stderr.on('data', d => { errOut += d.toString(); });
    proc.on('close', code => {
      if (code === 0) resolve();
      else reject(new Error(`ffmpeg exited ${code}: ${errOut.slice(-300)}`));
    });
  });
}

async function processSlug(slug) {
  const includeDir = join(sourceRoot, slug, 'include');

  const allFiles = await readdir(includeDir).catch(() => null);
  if (allFiles === null) {
    console.log(`  [${slug}] no "include" subfolder found — skipping`);
    return;
  }

  const photos = allFiles.filter(f => PHOTO_EXT.test(f)).sort();
  const gifs   = allFiles.filter(f => GIF_EXT.test(f)).sort();
  const mp4s   = allFiles.filter(f => MP4_EXT.test(f)).sort();

  const total = photos.length + gifs.length + mp4s.length;
  if (total === 0) {
    console.log(`  [${slug}] "include" folder has no supported files — skipping`);
    return;
  }

  console.log(`  [${slug}] ${photos.length} photo(s), ${gifs.length} GIF(s), ${mp4s.length} MP4(s)`);

  const slugDestDir = join(destRoot, slug);
  await mkdir(slugDestDir, { recursive: true });

  let imported = 0;
  let skipped  = 0;

  // ── Photos: compress + sequential rename ──────────────────────────────────
  for (let i = 0; i < photos.length; i++) {
    const num      = String(i + 1).padStart(2, '0');
    const srcFile  = join(includeDir, photos[i]);
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
      console.error(`    ERROR compressing ${photos[i]}: ${err.message}`);
    }
  }

  // ── GIFs: convert to MP4, keep base name ─────────────────────────────────
  for (const gif of gifs) {
    const base     = basename(gif, extname(gif));
    const srcFile  = join(includeDir, gif);
    const destFile = join(slugDestDir, `${base}.mp4`);

    if (await fileExists(destFile)) {
      console.log(`    ${base}.mp4 already exists — skipping`);
      skipped++;
      continue;
    }

    try {
      await ffmpegConvert(srcFile, destFile);
      console.log(`    ${gif} → ${base}.mp4`);
      imported++;
    } catch (err) {
      console.error(`    ERROR converting ${gif}: ${err.message}`);
    }
  }

  // ── MP4s: copy as-is ─────────────────────────────────────────────────────
  for (const mp4 of mp4s) {
    const srcFile  = join(includeDir, mp4);
    const destFile = join(slugDestDir, mp4);

    if (await fileExists(destFile)) {
      console.log(`    ${mp4} already exists — skipping`);
      skipped++;
      continue;
    }

    try {
      await copyFile(srcFile, destFile);
      console.log(`    ${mp4} → ${mp4} (copied)`);
      imported++;
    } catch (err) {
      console.error(`    ERROR copying ${mp4}: ${err.message}`);
    }
  }

  console.log(`  [${slug}] done — ${imported} imported, ${skipped} already existed`);
}

async function main() {
  const entries  = await readdir(sourceRoot, { withFileTypes: true });
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

  console.log('✓ Import complete. Files saved to: public/images/sabbatical/');
  console.log('');
  console.log('To reference a video in markdown:');
  console.log('  <video autoplay loop muted playsinline class="w-full rounded-xl my-6">');
  console.log('    <source src="/images/sabbatical/<slug>/filename.mp4" type="video/mp4">');
  console.log('  </video>');
  console.log('');
  console.log('Pages with mixed text/video/photos should use: layout: "inline"');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
