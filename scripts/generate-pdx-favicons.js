/**
 * generate-pdx-favicons.js
 *
 * Rasterizes public-pdx-events/favicon.svg into the PNG/ICO set that search
 * engines and devices expect. DuckDuckGo and Bing don't use SVG favicons —
 * they fetch /favicon.ico or a PNG <link rel="icon"> (Bing wants a multiple
 * of 48px). Re-run after changing the SVG:  node scripts/generate-pdx-favicons.js
 */

import sharp from 'sharp';
import { readFileSync, writeFileSync } from 'fs';

const dir = 'public-pdx-events';
const svg = readFileSync(`${dir}/favicon.svg`);

const render = (size, bg) => {
  let img = sharp(svg, { density: 72 * (size / 32) * 2 }).resize(size, size);
  if (bg) img = img.flatten({ background: bg });
  return img.png().toBuffer();
};

// Square PNGs
const pngs = {
  'favicon-48x48.png': 48,
  'favicon-96x96.png': 96,
  'icon-192.png': 192,
  'icon-512.png': 512,
};
for (const [name, size] of Object.entries(pngs)) {
  writeFileSync(`${dir}/${name}`, await render(size));
}

// Apple touch icon: iOS fills transparency with black, so pad on white
const inner = await render(150);
writeFileSync(
  `${dir}/apple-touch-icon.png`,
  await sharp({ create: { width: 180, height: 180, channels: 4, background: '#ffffff' } })
    .composite([{ input: inner, gravity: 'center' }])
    .png()
    .toBuffer()
);

// favicon.ico with PNG-encoded 16/32/48 entries
const icoSizes = [16, 32, 48];
const images = await Promise.all(icoSizes.map((s) => render(s)));
const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // type: icon
header.writeUInt16LE(images.length, 4);
const entries = [];
let offset = 6 + 16 * images.length;
images.forEach((buf, i) => {
  const e = Buffer.alloc(16);
  e.writeUInt8(icoSizes[i], 0); // width
  e.writeUInt8(icoSizes[i], 1); // height
  e.writeUInt8(0, 2); // palette
  e.writeUInt8(0, 3); // reserved
  e.writeUInt16LE(1, 4); // color planes
  e.writeUInt16LE(32, 6); // bpp
  e.writeUInt32LE(buf.length, 8);
  e.writeUInt32LE(offset, 12);
  offset += buf.length;
  entries.push(e);
});
writeFileSync(`${dir}/favicon.ico`, Buffer.concat([header, ...entries, ...images]));

console.log('Wrote favicon.ico, apple-touch-icon.png, and', Object.keys(pngs).join(', '));
