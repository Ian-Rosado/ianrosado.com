// schema.org Event structured data (JSON-LD) for the events rendered in a
// page's HTML. Search engines' event features and AI answer engines read this
// instead of parsing the visible rows.

import type { CalEvent } from './google-calendar';

const HAS_REGION = /\b(OR|Oregon|WA|Washington)\b|\b\d{5}\b/;

// "Venue, 123 SE Street, Portland, OR" → name "Venue", address the rest.
// A location that starts with a street number is all address.
function place(location: string) {
  const flat = location.split('\n').map((l) => l.trim()).filter(Boolean).join(', ');
  if (!flat) return { '@type': 'Place', name: 'Portland, OR', address: 'Portland, OR' };
  const [first, ...rest] = flat.split(/,\s*/);
  const named = rest.length > 0 && !/^\d/.test(first);
  let address = named ? rest.join(', ') : flat;
  if (!HAS_REGION.test(address)) address += ', Portland, OR';
  return { '@type': 'Place', name: named ? first : flat, address };
}

function offer(e: CalEvent) {
  const base = { '@type': 'Offer', priceCurrency: 'USD' };
  if (e.costClass === 'free') return { ...base, price: 0 };
  const m = e.cost.match(/\$\s?(\d[\d,]*(?:\.\d+)?)/);
  return m ? { ...base, price: Number(m[1].replace(/,/g, '')) } : null;
}

function toEvent(e: CalEvent) {
  const url = e.url || e.googleUrl;
  const offers = offer(e);
  return {
    '@type': 'Event',
    // Some scraped titles carry a "[comedy] " source prefix
    name: e.title.replace(/^\[[^\]]+\]\s*/, ''),
    startDate: e.start,
    ...(e.end && e.end !== e.start ? { endDate: e.end } : {}),
    eventStatus: 'https://schema.org/EventScheduled',
    eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    location: place(e.location),
    ...(url ? { url } : {}),
    ...(offers ? { offers } : {}),
  };
}

// JSON string for a <script type="application/ld+json">. Multi-day events
// appear once per day in the rows but once here. `<` is escaped so a title
// can't close the script tag.
export function eventsJsonLd(events: CalEvent[]): string {
  const seen = new Set<string>();
  const items = [];
  for (const e of events) {
    const key = `${e.start}|${e.title}|${e.location}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push(toEvent(e));
  }
  return JSON.stringify({ '@context': 'https://schema.org', '@graph': items }).replace(/</g, '\\u003c');
}
