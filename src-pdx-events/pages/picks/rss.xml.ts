// RSS feed of the weekly picks: one item per roundup, newest first.
import { ROUNDUPS, longDate, roundupTitle, roundupDescription } from '../../lib/picks';

const SITE = 'https://www.pdx-events.com';

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Posts go up the day before a roundup starts (Sunday / Thursday), 9am Pacific
function pubDate(start: string): string {
  const d = new Date(start + 'T16:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toUTCString();
}

export function GET() {
  const items = ROUNDUPS.slice(0, 30).map((r) => {
    const url = `${SITE}/picks/${r.id}/`;
    const body = r.picks
      .map((p) => `<p><strong>${esc(p.name)}</strong> — ${esc(longDate(p.date || r.start))}${p.venue ? `, ${esc(p.venue)}` : ''}${p.details ? ` · ${esc(p.details)}` : ''}<br>${esc(p.description)}</p>`)
      .join('');
    return `<item>
  <title>${esc(roundupTitle(r))}</title>
  <link>${url}</link>
  <guid isPermaLink="true">${url}</guid>
  <pubDate>${pubDate(r.start)}</pubDate>
  <description>${esc(roundupDescription(r))}</description>
  <content:encoded><![CDATA[${body.replace(/]]>/g, ']]&gt;')}]]></content:encoded>
</item>`;
  });

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>PDX Events — Weekly Picks</title>
  <link>${SITE}/picks/</link>
  <atom:link href="${SITE}/picks/rss.xml" rel="self" type="application/rss+xml" />
  <description>Hand-picked things to do in Portland, Oregon — every week and every weekend.</description>
  <language>en-us</language>
${items.join('\n')}
</channel>
</rss>
`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' } });
}
