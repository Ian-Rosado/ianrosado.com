/**
 * vercel-build.js
 *
 * Vercel runs this instead of `npm run build` because it's registered as
 * the "vercel-build" script in package.json.
 *
 * Set BUILD_TARGET=pdx-events in the pdx-events.com Vercel project's
 * environment variables to build that site. All other projects (including
 * ianrosado.com) get the default `astro build`.
 */

import { execSync } from 'child_process';

const cmd = process.env.BUILD_TARGET === 'pdx-events'
  ? 'npm run build:pdx-events'
  : 'npm run build';

console.log(`[vercel-build] BUILD_TARGET=${process.env.BUILD_TARGET ?? '(not set)'}`);
console.log(`[vercel-build] Running: ${cmd}`);

execSync(cmd, { stdio: 'inherit' });
