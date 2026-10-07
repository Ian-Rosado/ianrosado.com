// Landing pages for pdx-events.com: one statically built page per category,
// time window ("today", "this weekend") and trivia night, each answering a
// specific search ("trivia nights portland", "free things to do in portland").
// Unlike the homepage — which server-renders only 3 days and loads the rest
// with JS — these put every listed event in the HTML (plus Event JSON-LD),
// so crawlers that don't run JavaScript see them. Built by
// src-pdx-events/pages/[...landing].astro; rebuilt with the 6-hourly deploy.

import { TODAY_STR, addDaysStr, groupByDate, type CalEvent } from './google-calendar';

export type Day = [date: string, events: CalEvent[]];

// Facts about the selected events, for the page copy
export interface PageStats {
  count: number;
  freeCount: number;
  days: number;       // calendar days covered, from the window start
  firstDate: string;
  lastDate: string;
}

export interface LandingPage {
  slug: string;       // URL path, no slashes at the ends
  label: string;      // short link text
  title: string;      // <title> (Layout appends " | PDX Events")
  h1: string;
  description: (s: PageStats) => string;
  intro: (s: PageStats) => string;
  filter: (e: CalEvent) => boolean;
  // Window: `from`/`to` dates (inclusive), else today + maxDays - 1
  window?: () => { from: string; to: string };
  maxDays: number;
  // Stop adding whole days once this many events are listed (keeps the HTML
  // reasonable on busy categories; the first day is always included)
  maxEvents: number;
  related: string[];  // slugs linked under the list
  calendar?: string;  // calendar slug: offer subscribe links for it
}

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}

function weekday(ymd: string): number {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

// "Oct 9" / "Oct 9–11" / "Oct 30 – Nov 1"
export function formatRange(from: string, to: string): string {
  const f = (ymd: string, opts: Intl.DateTimeFormatOptions) =>
    new Date(ymd + 'T12:00:00Z').toLocaleDateString('en-US', { timeZone: 'UTC', ...opts });
  if (from === to) return f(from, { month: 'short', day: 'numeric' });
  if (from.slice(0, 7) === to.slice(0, 7)) return `${f(from, { month: 'short', day: 'numeric' })}–${f(to, { day: 'numeric' })}`;
  return `${f(from, { month: 'short', day: 'numeric' })} – ${f(to, { month: 'short', day: 'numeric' })}`;
}

// Fri–Sun: the current weekend if it's already Fri/Sat/Sun, else the next one
function weekendWindow() {
  const wd = weekday(TODAY_STR);
  const from = wd === 5 || wd === 6 || wd === 0 ? TODAY_STR : addDaysStr(TODAY_STR, 5 - wd);
  return { from, to: addDaysStr(from, (7 - weekday(from)) % 7) };
}

// The next occurrence (today included) of a weekday
function nextWeekday(target: number) {
  const from = addDaysStr(TODAY_STR, (target - weekday(TODAY_STR) + 7) % 7);
  return { from, to: from };
}

const bySlug = (slug: string) => (e: CalEvent) => e.calendarSlug === slug;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const CATEGORY_LINKS = ['today', 'this-weekend', 'free', 'live-music', 'trivia', 'farmers-markets', 'comedy', 'karaoke', 'sports', 'bike-rides'];

const MAIN: LandingPage[] = [
  {
    slug: 'today',
    label: 'Today',
    title: 'Things to Do in Portland Today',
    h1: 'Things to Do in Portland Today',
    description: (s) => `${plural(s.count, 'event')} happening in Portland, OR today (${formatRange(s.firstDate, s.firstDate)}) — ${s.freeCount} free. Live music, trivia, markets, comedy, and more.`,
    intro: (s) => `Everything on the PDX Events calendars for today — ${plural(s.count, 'event')}, ${s.freeCount} of them free. Concerts, trivia nights, comedy, bike rides, markets and one-off happenings around Portland.`,
    filter: () => true,
    window: () => ({ from: TODAY_STR, to: TODAY_STR }),
    maxDays: 1,
    maxEvents: 700,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'this-weekend',
    label: 'This weekend',
    title: 'Things to Do in Portland This Weekend',
    h1: 'Things to Do in Portland This Weekend',
    description: (s) => `${plural(s.count, 'event')} in Portland this weekend (${formatRange(s.firstDate, s.lastDate)}) — ${s.freeCount} free. Festivals, concerts, markets, comedy and more.`,
    intro: (s) => `The full Portland lineup for ${formatRange(s.firstDate, s.lastDate)}: ${plural(s.count, 'event')} across festivals, concerts, farmers markets, comedy, sports and bike rides — ${s.freeCount} of them free.`,
    filter: () => true,
    window: weekendWindow,
    maxDays: 3,
    maxEvents: 900,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'free',
    label: 'Free',
    title: 'Free Things to Do in Portland This Week',
    h1: 'Free Things to Do in Portland',
    description: (s) => `${plural(s.count, 'free event')} in Portland, OR over the next ${plural(s.days, 'day')} — free concerts, trivia, farmers markets, bike rides, and community events.`,
    intro: (s) => `${plural(s.count, 'free event')} over the next ${plural(s.days, 'day')}: no-cover shows, trivia nights, farmers markets, community bike rides, and free festivals and gatherings around Portland.`,
    filter: (e) => e.costClass === 'free',
    maxDays: 7,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'live-music',
    label: 'Live music',
    title: 'Live Music in Portland — Concerts & Shows This Week',
    h1: 'Live Music in Portland',
    description: (s) => `${plural(s.count, 'concert')} and live shows in Portland, OR over the next ${plural(s.days, 'day')} — clubs, bars, theaters and big venues, with ${s.freeCount} free shows.`,
    intro: (s) => `${plural(s.count, 'show')} over the next ${plural(s.days, 'day')} at Portland's clubs, bars, theaters and arenas — ${s.freeCount} of them free or no cover.`,
    filter: bySlug('live-music'),
    calendar: 'live-music',
    maxDays: 7,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'trivia',
    label: 'Trivia nights',
    title: 'Trivia Nights in Portland — Weekly Pub Quiz Schedule',
    h1: 'Trivia Nights in Portland',
    description: (s) => `Every weekly trivia night and pub quiz in Portland, OR — ${plural(s.count, 'game')} this week at bars and breweries in N/NE, NW/SW, SE Portland and the suburbs.`,
    intro: (s) => `Portland's pub quiz scene runs every night of the week. This is the full schedule for the next seven days — ${plural(s.count, 'game')} at bars, breweries and pizza places across the city and suburbs. Nearly all are free to play; on busy nights, arrive 15–30 minutes early to get a table.`,
    filter: bySlug('trivia'),
    calendar: 'trivia',
    maxDays: 7,
    maxEvents: 600,
    related: [...WEEKDAYS.slice(1), WEEKDAYS[0]].map((d) => `trivia/${d}`),
  },
  {
    slug: 'farmers-markets',
    label: 'Farmers markets',
    title: 'Portland Farmers Markets — Schedule & Hours',
    h1: 'Portland Farmers Markets',
    description: (s) => `Portland-area farmers market schedule for the next ${plural(s.days, 'day')} — ${plural(s.count, 'market day')}, with times and locations from Portland to Beaverton, Hillsboro, Gresham and Vancouver.`,
    intro: (s) => `${plural(s.count, 'market day')} over the next ${plural(s.days, 'day')} across the Portland metro — the PSU Saturday market, neighborhood markets like Hollywood, Moreland and St. Johns, and suburban markets in Beaverton, Hillsboro, Gresham and beyond. Free to browse.`,
    filter: bySlug('farmers-markets'),
    calendar: 'farmers-markets',
    maxDays: 28,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'comedy',
    label: 'Comedy',
    title: 'Comedy Shows in Portland — Stand-Up, Improv & Open Mics',
    h1: 'Comedy in Portland',
    description: (s) => `${plural(s.count, 'comedy show')} in Portland, OR over the next ${plural(s.days, 'day')} — stand-up, improv and open mics, ${s.freeCount} free.`,
    intro: (s) => `${plural(s.count, 'show')} over the next ${plural(s.days, 'day')}: touring headliners, local showcases, improv and open mics — ${s.freeCount} of them free.`,
    filter: bySlug('comedy'),
    calendar: 'comedy',
    maxDays: 28,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'karaoke',
    label: 'Karaoke',
    title: 'Karaoke Nights in Portland',
    h1: 'Karaoke in Portland',
    description: (s) => `Karaoke nights at Portland bars and venues — ${plural(s.count, 'night')} over the next ${plural(s.days, 'day')}, including themed and live-band karaoke.`,
    intro: (s) => `${plural(s.count, 'karaoke night')} over the next ${plural(s.days, 'day')} — regular bar karaoke plus themed nights and live-band karaoke.`,
    filter: bySlug('karaoke'),
    calendar: 'karaoke',
    maxDays: 28,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'sports',
    label: 'Sports',
    title: 'Portland Sports Schedule — Home Games',
    h1: 'Portland Sports Schedule',
    description: (s) => `Home games in Portland, OR for the next ${plural(s.days, 'day')} — Timbers, Thorns, Trail Blazers, Winterhawks, Portland Pilots, roller derby and more (${plural(s.count, 'game')}).`,
    intro: (s) => `${plural(s.count, 'home game')} over the next ${plural(s.days, 'day')} — pro soccer, basketball and hockey, University of Portland Pilots, roller derby and more.`,
    filter: bySlug('sports'),
    calendar: 'sports',
    maxDays: 90,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
  {
    slug: 'bike-rides',
    label: 'Bike rides',
    title: 'Portland Group Bike Rides — Shift & Pedalpalooza',
    h1: 'Group Bike Rides in Portland',
    description: (s) => `${plural(s.count, 'group bike ride')} in Portland over the next ${plural(s.days, 'day')} — Shift community rides year-round and Pedalpalooza every summer. Nearly all free.`,
    intro: (s) => `${plural(s.count, 'ride')} over the next ${plural(s.days, 'day')} from the Shift community calendar — themed social rides, slow rides and explorations. Every summer they become Pedalpalooza, weeks of rides all over the city. Nearly all are free and open to anyone with a bike.`,
    filter: bySlug('pedalpalooza'),
    calendar: 'pedalpalooza',
    maxDays: 28,
    maxEvents: 450,
    related: CATEGORY_LINKS,
  },
];

const TRIVIA_DAYS: LandingPage[] = WEEKDAYS.map((day, i) => ({
  slug: `trivia/${day}`,
  label: cap(day),
  title: `${cap(day)} Trivia Nights in Portland`,
  h1: `${cap(day)} Trivia in Portland`,
  description: (s) => `${plural(s.count, 'trivia night')} in Portland on ${cap(day)} (${formatRange(s.firstDate, s.firstDate)}) — pub quizzes at bars and breweries across the city and suburbs, nearly all free.`,
  intro: (s) => `Where to play trivia in Portland on a ${cap(day)}: ${plural(s.count, 'game')} this ${cap(day)}, ${formatRange(s.firstDate, s.firstDate)}. Most run weekly, so this is a good guide to any ${cap(day)}.`,
  filter: bySlug('trivia'),
  calendar: 'trivia',
  window: () => nextWeekday(i),
  maxDays: 1,
  maxEvents: 600,
  related: ['trivia', ...[...WEEKDAYS.slice(1), WEEKDAYS[0]].filter((d) => d !== day).map((d) => `trivia/${d}`)],
}));

export const LANDING_PAGES: LandingPage[] = [...MAIN, ...TRIVIA_DAYS];
export const LANDING_BY_SLUG = new Map(LANDING_PAGES.map((p) => [p.slug, p]));
// Links shown in the site footer / homepage
export const FOOTER_LINKS = CATEGORY_LINKS.map((s) => LANDING_BY_SLUG.get(s)!);

export function selectDays(all: CalEvent[], page: LandingPage): { days: Day[]; stats: PageStats } {
  const { from, to } = page.window?.() ?? { from: TODAY_STR, to: addDaysStr(TODAY_STR, page.maxDays - 1) };
  const inWindow = all.filter((e) => e.date >= from && e.date <= to && page.filter(e));
  const days: Day[] = [];
  let count = 0;
  let end = to; // last date covered; earlier than `to` if maxEvents cut the list short
  for (const [date, evs] of groupByDate(inWindow)) {
    if (days.length && count + evs.length > page.maxEvents) {
      end = addDaysStr(date, -1);
      break;
    }
    days.push([date, evs]);
    count += evs.length;
  }
  const listed = days.flatMap(([, evs]) => evs);
  return {
    days,
    stats: {
      count,
      freeCount: listed.filter((e) => e.costClass === 'free').length,
      days: daysBetween(from, end) + 1,
      firstDate: days[0]?.[0] ?? from,
      lastDate: days.at(-1)?.[0] ?? to,
    },
  };
}
