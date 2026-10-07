// /llms.txt (llmstxt.org): a plain-markdown map of the site for AI agents —
// what each page covers, the machine-readable feeds, and this week's picks.
// Rebuilt with every deploy, so the counts and picks stay current.
import { LANDING_PAGES, selectDays } from '../../src-shared/lib/landing-pages';
import { fetchAllEvents } from '../../src-shared/lib/events';
import { SUBSCRIBABLE, subscribeLinks } from '../../src-shared/lib/calendars';
import { currentWeek, longDate, rangeLabel } from '../lib/picks';

const SITE = 'https://www.pdx-events.com';

export async function GET() {
  const events = await fetchAllEvents();
  const pages = LANDING_PAGES.map((p) => {
    const { stats } = selectDays(events, p);
    return `- [${p.h1}](${SITE}/${p.slug}/): ${p.description(stats)}`;
  });
  const week = currentWeek();
  const picks = week
    ? week.picks.map((p) => `- ${longDate(p.date || week.start)}: **${p.name}**${p.venue ? ` at ${p.venue}` : ''}${p.details ? ` (${p.details})` : ''} — ${p.description}`)
    : [];

  const body = `# PDX Events

> A hand-curated calendar of things to do in Portland, Oregon: ${events.length} upcoming events over the next 90 days — festivals, live music, comedy, trivia nights, farmers markets, sports, karaoke and group bike rides — plus a weekly list of hand-picked highlights. Run by Ian Rosado, a Portland resident; no sponsored listings.

Listings give the date, time and venue/address, the cost (or "Free") when known, and a link to the event's own page. Pages are rebuilt from the source calendars every 6 hours.

## Main pages

- [All Portland events](${SITE}/): searchable list and month calendar of every upcoming event, with FAQ.
- [Weekly picks](${SITE}/picks/): the best things to do in Portland this week, hand-picked, with a short description of each.
- [Subscribe](${SITE}/subscribe/): add any of the calendars to Google Calendar, Apple Calendar or Outlook.
- [Portland favorites](${SITE}/favorites/): Ian's favorite Portland restaurants, coffee, parks and spots.
- [Pickup soccer](${SITE}/pickup-soccer/): where and when to find pickup soccer games in Portland.
- [About](${SITE}/about/)

## Events by category and date

${pages.join('\n')}

## Machine-readable data

- [events.json](${SITE}/events.json): every upcoming event (90 days). Shape: \`{ cats: [slug, cssClass, calendarName][], days: [date, [catIndex, time, title, location, mapsQuery, cost, costClass, url][]][] }\`. \`costClass\` is free | paid | unknown.
- [Weekly picks RSS](${SITE}/picks/rss.xml)
- Event pages also carry schema.org Event JSON-LD.
- iCal feeds (one per calendar):
${SUBSCRIBABLE.map((c) => `  - ${c.name}: ${subscribeLinks(c).ical.replace('webcal://', 'https://')}`).join('\n')}
${week ? `
## This week's picks (${rangeLabel(week)})

${picks.join('\n')}
` : ''}`;

  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
