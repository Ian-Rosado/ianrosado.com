import {
  CALENDARS,
  TRIVIA_CALENDARS,
  TRIVIA_GROUP,
  PEDALPALOOZA_CALENDAR,
} from './calendars';
import {
  fetchCalendarEvents,
  fetchMultipleCalendars,
  type CalEvent,
} from './google-calendar';

// A category shown in the filter bar / used to color the calendar grid.
export interface EventCategory {
  slug: string;
  label: string;
  color: string;
}

export const EVENT_CATEGORIES: EventCategory[] = [
  { slug: 'events', label: 'Events', color: 'orange' },
  { slug: 'live-music', label: 'Live Music', color: 'yellow' },
  { slug: 'comedy', label: 'Comedy', color: 'purple' },
  { slug: 'karaoke', label: 'Karaoke', color: 'pink' },
  { slug: 'farmers-markets', label: 'Markets', color: 'green' },
  { slug: 'sports', label: 'Sports', color: 'red' },
  { slug: 'trivia', label: 'Trivia', color: 'blue' },
  { slug: 'pedalpalooza', label: 'Pedalpalooza', color: 'teal' },
];

// Fetch every calendar in parallel and return one flat, date-sorted list.
// Trivia is fetched as a group (4 sub-calendars) but all carry slug 'trivia'
// and the group's display name.
export async function fetchAllEvents(): Promise<CalEvent[]> {
  const results = await Promise.all([
    ...CALENDARS.map((c) => fetchCalendarEvents(c.id, c.name, c.slug, c.color)),
    fetchMultipleCalendars(
      TRIVIA_CALENDARS.map((c) => ({ id: c.id, name: TRIVIA_GROUP.name, slug: c.slug, color: c.color })),
    ),
    fetchCalendarEvents(
      PEDALPALOOZA_CALENDAR.id,
      PEDALPALOOZA_CALENDAR.name,
      PEDALPALOOZA_CALENDAR.slug,
      PEDALPALOOZA_CALENDAR.color,
    ),
  ]);

  return results
    .flat()
    .sort((a, b) => a.date.localeCompare(b.date) || a.sortKey - b.sortKey);
}
