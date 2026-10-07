// Ian's weekly picks — the "Events of the Week" (Mon–Sun) and "Plan Your
// Weekend" (Fri–Sun) Instagram posts, published as /picks/ pages. The JSON in
// src-pdx-events/data/picks/ is exported from each post's event cards by
// scripts/add-to-calendar/export_picks.py.

import { TODAY_STR } from '../../src-shared/lib/google-calendar';

export interface Pick {
  date: string;        // YYYY-MM-DD
  endDate?: string;    // multi-day picks
  time: string;        // HH:MM (24h) or ''
  slot: 'day' | 'night' | null;
  emoji: string;
  category: string;
  name: string;
  description: string;
  venue: string;
  details: string;     // e.g. "7 PM · Free"
  free: boolean;
}

export interface Roundup {
  id: string;          // week-of-2026-10-05 / weekend-of-2026-10-02
  type: 'week' | 'weekend';
  start: string;
  end: string;
  picks: Pick[];
}

const files = import.meta.glob<Roundup>('../data/picks/*.json', { eager: true, import: 'default' });

// Newest first
export const ROUNDUPS: Roundup[] = Object.values(files).sort((a, b) => b.start.localeCompare(a.start) || a.type.localeCompare(b.type));

// The week to feature on /picks/: the one covering today, else the most recent
// one that has started, else the newest.
export function currentWeek(): Roundup | undefined {
  const weeks = ROUNDUPS.filter((r) => r.type === 'week');
  return weeks.find((r) => r.start <= TODAY_STR && TODAY_STR <= r.end)
    ?? weeks.find((r) => r.start <= TODAY_STR)
    ?? weeks[0];
}

// A weekend roundup that hasn't ended and starts within the week
export function currentWeekend(): Roundup | undefined {
  return ROUNDUPS.filter((r) => r.type === 'weekend' && r.end >= TODAY_STR)
    .sort((a, b) => a.start.localeCompare(b.start))[0];
}

const fmt = (ymd: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(ymd + 'T12:00:00Z').toLocaleDateString('en-US', { timeZone: 'UTC', ...opts });

// "Oct 5–11, 2026" / "Sep 28 – Oct 4, 2026"
export function rangeLabel(r: Roundup): string {
  const year = r.end.slice(0, 4);
  if (r.start.slice(0, 7) === r.end.slice(0, 7)) {
    return `${fmt(r.start, { month: 'short', day: 'numeric' })}–${fmt(r.end, { day: 'numeric' })}, ${year}`;
  }
  return `${fmt(r.start, { month: 'short', day: 'numeric' })} – ${fmt(r.end, { month: 'short', day: 'numeric' })}, ${year}`;
}

export const longDate = (ymd: string) => fmt(ymd, { weekday: 'long', month: 'long', day: 'numeric' });

export function roundupTitle(r: Roundup): string {
  return r.type === 'week'
    ? `Best Things to Do in Portland: Week of ${rangeLabel(r)}`
    : `Portland Weekend Picks: ${rangeLabel(r)}`;
}

export function roundupDescription(r: Roundup): string {
  const names = r.picks.slice(0, 3).map((p) => p.name).join(', ');
  const what = r.type === 'week' ? 'events for the week' : 'weekend events';
  return `${r.picks.length} hand-picked ${what} in Portland, OR (${rangeLabel(r)}): ${names}, and more — with times, places, and what makes each worth going to.`;
}

// Picks grouped by date, in order
export function byDate(r: Roundup): [string, Pick[]][] {
  const map = new Map<string, Pick[]>();
  for (const p of r.picks) {
    const k = p.date || r.start;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(p);
  }
  return [...map.entries()];
}

// Pacific UTC offset ("-07:00") on a date
function pacificOffset(ymd: string): string {
  const name = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', timeZoneName: 'shortOffset' })
    .formatToParts(new Date(ymd + 'T20:00:00Z'))
    .find((p) => p.type === 'timeZoneName')?.value ?? 'GMT-8';
  const m = name.match(/GMT([+-])(\d{1,2})/);
  return m ? `${m[1]}${m[2].padStart(2, '0')}:00` : '-08:00';
}

// schema.org Event JSON-LD for a roundup's picks (`<` escaped for <script>)
export function picksJsonLd(r: Roundup): string {
  const events = r.picks.filter((p) => p.date).map((p) => ({
    '@type': 'Event',
    name: p.name,
    ...(p.description ? { description: p.description } : {}),
    startDate: p.time ? `${p.date}T${p.time}:00${pacificOffset(p.date)}` : p.date,
    ...(p.endDate ? { endDate: p.endDate } : {}),
    eventStatus: 'https://schema.org/EventScheduled',
    eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    location: {
      '@type': 'Place',
      name: p.venue || 'Portland, OR',
      address: /\b(OR|Oregon|WA)\b/.test(p.venue) ? p.venue : 'Portland, OR',
    },
    ...(p.free ? { isAccessibleForFree: true, offers: { '@type': 'Offer', price: 0, priceCurrency: 'USD' } } : {}),
  }));
  return JSON.stringify({ '@context': 'https://schema.org', '@graph': events }).replace(/</g, '\\u003c');
}

export function mapUrl(venue: string): string {
  const q = /\b(OR|Oregon|WA)\b/.test(venue) ? venue : `${venue}, Portland, OR`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
}
