import type { APIRoute } from 'astro';
import { CALENDARS, TRIVIA_CALENDARS, PEDALPALOOZA_CALENDAR } from '../lib/calendars';
import { fetchMultipleCalendars } from '../lib/google-calendar';

export const GET: APIRoute = async () => {
  const allCalendars = [
    ...CALENDARS.map(c => ({ id: c.id, name: c.name, slug: c.slug, color: c.color })),
    ...TRIVIA_CALENDARS.map(c => ({ id: c.id, name: c.name, slug: c.slug, color: c.color })),
    { id: PEDALPALOOZA_CALENDAR.id, name: PEDALPALOOZA_CALENDAR.name, slug: PEDALPALOOZA_CALENDAR.slug, color: PEDALPALOOZA_CALENDAR.color },
  ];

  const events = await fetchMultipleCalendars(allCalendars);

  const output = events.map(e => ({
    title: e.title,
    date: e.date,
    time: e.time || null,
    endTime: e.endTime || null,
    allDay: e.allDay,
    location: e.location || null,
    cost: e.cost || null,
    url: e.url || e.googleUrl || null,
    calendar: e.calendarName,
  }));

  return new Response(JSON.stringify({ updated: new Date().toISOString(), events: output }, null, 2), {
    headers: { 'Content-Type': 'application/json' },
  });
};
