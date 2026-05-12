/**
 * convert-gif.js
 *
 * Converts all .gif files in a directory (recursive) to .mp4.
 * Skips files that already have a matching .mp4 alongside them.
 * Uses ffmpeg-static (bundled binary — no separate ffmpeg install needed).
 *
 * Output settings:
 *   - H.264 video, yuv420p pixel format (broad browser compatibility)
 *   - CRF 23 quality (good balance of size vs. quality; lower = better)
 *   - faststart flag for web streaming
 *   - Dimensions rounded to even numbers (required by libx264)
 *
 * Usage:
 *   node scripts/convert-gif.js                             # all recipe folders
 *   node scripts/convert-gif.js public/images/recipes/simple-chocolate-mousse
 *   node scripts/convert-gif.js "C:\Users\you\Downloads\photos"
 *
 * In HTML/Markdown use as:
 *   <video autoplay loop muted playsinline>
 *     <source src="/images/recipes/slug/filename.mp4" type="video/mp4">
 *   </video>
 */

import ffmpegPath from 'ffmpeg-static';
import { readdir, stat } from 'fs/promises';
import { join, extname, basename, dirname } from 'path';
import { spawn } from 'child_process';

const DEFAULT_DIR = 'public/images/recipes';
const CRF = 23; // 0–51, lower = better quality / larger file. 18–28 is typical.

async function findGifFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await findGifFiles(full));
    } else if (extname(entry.name).toLowerCase() === '.gif') {
      files.push(full);
    }
  }
  return files;
}

function runFfmpeg(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(ffmpegPath, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = '';
    proc.stderr.on('data', chunk => { stderr += chunk.toString(); });
    proc.on('close', code => {
      if (code === 0) resolve();
      else reject(new Error(stderr.slice(-300))); // last 300 chars of ffmpeg output
    });
  });
}

async function convertFile(gifPath) {
  const mp4Path = join(dirname(gifPath), basename(gifPath, extname(gifPath)) + '.mp4');

  // Skip if MP4 already exists
  try {
    await stat(mp4Path);
    console.log(`  ⏭  Skipping (MP4 exists): ${basename(gifPath)}`);
    return { status: 'skipped' };
  } catch {
    // doesn't exist — proceed
  }

  const args = [
    '-i', gifPath,
    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', // ensure even dimensions for libx264
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',                        // broad compatibility (Safari, etc.)
    '-movflags', '+faststart',                    // stream before fully downloaded
    '-crf', String(CRF),
    '-y',                                         // overwrite without asking
    mp4Path,
  ];

  try {
    await runFfmpeg(args);
    const { size } = await stat(mp4Path);
    const { size: gifSize } = await stat(gifPath);
    const savings = Math.round((1 - size / gifSize) * 100);
    console.log(`  ✅ Saved:  ${basename(mp4Path)} (${mb(size)} MB — ${savings}% smaller than GIF)`);
    return { status: 'converted' };
  } catch (err) {
    console.log(`  ⚠️  Failed: ${basename(gifPath)} — ${err.message}`);
    return { status: 'failed' };
  }
}

function mb(bytes) {
  return (bytes / 1024 / 1024).toFixed(1);
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

  const files = await findGifFiles(targetDir);
  if (files.length === 0) {
    console.log(`No .gif files found in ${targetDir}`);
    process.exit(0);
  }

  console.log(`\nFound ${files.length} GIF(s) in ${targetDir}\n`);

  let converted = 0, skipped = 0, failed = 0;
  for (const file of files) {
    const result = await convertFile(file);
    if (result.status === 'converted') converted++;
    else if (result.status === 'skipped') skipped++;
    else failed++;
  }

  console.log(`\nDone! ${converted} converted, ${skipped} skipped, ${failed} failed.`);
  if (converted > 0) {
    console.log(`\nUse in markdown/HTML:`);
    console.log(`  <video autoplay loop muted playsinline>`);
    console.log(`    <source src="/images/recipes/SLUG/FILENAME.mp4" type="video/mp4">`);
    console.log(`  </video>`);
  }
}

main().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});
