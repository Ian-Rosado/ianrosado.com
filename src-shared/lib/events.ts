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
  { slug: 'trivia', label: 'Trivia', color: 'blue' },
  { slug: 'pedalpalooza', label: 'Pedalpalooza', color: 'teal' },
];

// Fetch every calendar in parallel and return one flat, date-sorted list.
// Trivia is fetched as a group (4 sub-calendars) but all carry slug 'trivia'.
export async function fetchAllEvents(): Promise<CalEvent[]> {
  const [
    eventsEvents,
    musicEvents,
    comedyEvents,
    karaokeEvents,
    marketsEvents,
    triviaEvents,
    pedalaEvents,
  ] = await Promise.all([
    fetchCalendarEvents(CALENDARS[0].id, CALENDARS[0].name, CALENDARS[0].slug, CALENDARS[0].color),
    fetchCalendarEvents(CALENDARS[1].id, CALENDARS[1].name, CALENDARS[1].slug, CALENDARS[1].color),
    fetchCalendarEvents(CALENDARS[2].id, CALENDARS[2].name, CALENDARS[2].slug, CALENDARS[2].color),
    fetchCalendarEvents(CALENDARS[3].id, CALENDARS[3].name, CALENDARS[3].slug, CALENDARS[3].color),
    fetchCalendarEvents(CALENDARS[4].id, CALENDARS[4].name, CALENDARS[4].slug, CALENDARS[4].color),
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

  return [
    ...eventsEvents,
    ...musicEvents,
    ...comedyEvents,
    ...karaokeEvents,
    ...marketsEvents,
    ...triviaEvents,
    ...pedalaEvents,
  ].sort((a, b) => a.date.localeCompare(b.date) || a.sortKey - b.sortKey);
}
