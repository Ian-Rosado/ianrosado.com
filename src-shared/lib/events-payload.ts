// Compact JSON payload of every upcoming event, served as /events.json by each
// site. EventsView only server-renders the first few days (keeps the HTML
// small for phones and crawlers) and renders the rest from this file.
//
// Shape (arrays instead of objects to keep it small):
//   cats: [slug, dotClass, calendarName][]
//   days: [date, EventTuple[]][]
//   EventTuple: [catIdx, time, title, location, mapQuery, cost, costClass, link]
// `mapQuery` is the Google Maps URL with MAP_PREFIX stripped ('' = no link).

import { COLOR_MAP } from './calendars';
import { fetchAllEvents } from './events';
import { groupByDate, type CalEvent } from './google-calendar';

export const MAP_PREFIX = 'https://www.google.com/maps/search/?api=1&query=';

export type EventTuple = [number, string, string, string, string, string, string, string];
export interface EventsPayload {
  cats: [string, string, string][];
  days: [string, EventTuple[]][];
}

export function buildEventsPayload(events: CalEvent[]): EventsPayload {
  const cats: [string, string, string][] = [];
  const catIdx = new Map<string, number>();

  const days = [...groupByDate(events).entries()].map(([date, evs]) => [
    date,
    evs.map((e): EventTuple => {
      const dot = (COLOR_MAP[e.color] ?? COLOR_MAP['orange']).dot;
      const key = `${e.calendarSlug}|${dot}|${e.calendarName}`;
      if (!catIdx.has(key)) {
        catIdx.set(key, cats.length);
        cats.push([e.calendarSlug, dot, e.calendarName]);
      }
      return [
        catIdx.get(key)!,
        e.allDay ? 'all day' : e.time,
        e.title,
        e.location || '',
        e.mapUrl ? e.mapUrl.slice(MAP_PREFIX.length) : '',
        e.cost || '',
        e.costClass,
        e.url || e.googleUrl || '',
      ];
    }),
  ]) as [string, EventTuple[]][];

  return { cats, days };
}

// Shared GET handler for each site's /events.json endpoint
export async function eventsJsonResponse(): Promise<Response> {
  const payload = buildEventsPayload(await fetchAllEvents());
  return new Response(JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });
}
