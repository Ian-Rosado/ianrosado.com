const API_KEY = import.meta.env.GOOGLE_CALENDAR_API_KEY;
const BASE = 'https://www.googleapis.com/calendar/v3/calendars';
const TZ = 'America/Los_Angeles';
const DAYS_AHEAD = 45;

export interface CalEvent {
  id: string;
  title: string;
  date: string;        // YYYY-MM-DD (Pacific)
  time: string;        // h:mm AM/PM, or '' for all-day
  endTime: string;     // h:mm AM/PM, or ''
  allDay: boolean;
  location: string;
  cost: string;
  url: string;         // source URL (from description line 2)
  googleUrl: string;   // link to Google Calendar event
  calendarName: string;
  calendarSlug: string;
  color: string;
}

// Strip HTML tags and decode common entities
function stripHtml(s: string): string {
  return s
    .replace(/<[^>]+>/g, ' ')           // remove tags
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Normalize a cost string — keep the price part, drop trailing descriptions
function normalizeCost(raw: string): string {
  // Keep only up to the first | or ; or — (description often follows)
  const trimmed = raw.split(/[|;—–]/)[0].trim();
  // Must look like a price or free/pwyc
  if (/free|pwyc|pay what|\$|\d/.test(trimmed.toLowerCase())) {
    return trimmed;
  }
  return '';
}

// Parse cost + source URL out of the description field
// Format written by add-to-calendar script: "cost\nurl"
function parseDescription(desc: string): { cost: string; url: string } {
  const clean = stripHtml(desc || '');
  const lines = clean.split('\n').map(l => l.trim()).filter(Boolean);
  let cost = '';
  let url = '';
  for (const line of lines) {
    // Extract any URL from the line (handles "text https://... more text")
    const urlMatch = line.match(/https?:\/\/\S+/);
    if (urlMatch && !url) {
      url = urlMatch[0].replace(/[.,)>'"]+$/, ''); // strip trailing punctuation
    } else if (!cost) {
      const c = normalizeCost(line);
      if (c) cost = c;
    }
  }
  return { cost, url };
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true, timeZone: TZ,
  });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-CA', { timeZone: TZ }); // YYYY-MM-DD
}

function toCalEvent(
  item: any,
  calendarName: string,
  calendarSlug: string,
  color: string,
): CalEvent | null {
  const title = item.summary?.trim();
  if (!title) return null;

  const startRaw = item.start?.dateTime ?? item.start?.date ?? '';
  const endRaw   = item.end?.dateTime   ?? item.end?.date   ?? '';
  if (!startRaw) return null;

  const allDay = !item.start?.dateTime;
  const date    = allDay ? startRaw : formatDate(startRaw);
  const time    = allDay ? '' : formatTime(startRaw);
  const endTime = allDay ? '' : (endRaw ? formatTime(endRaw) : '');

  const { cost, url } = parseDescription(item.description ?? '');

  return {
    id: item.id,
    title,
    date,
    time,
    endTime,
    allDay,
    location: item.location?.trim() ?? '',
    cost,
    url,
    googleUrl: item.htmlLink ?? '',
    calendarName,
    calendarSlug,
    color,
  };
}

export async function fetchCalendarEvents(
  calendarId: string,
  calendarName: string,
  calendarSlug: string,
  color: string,
): Promise<CalEvent[]> {
  if (!API_KEY) {
    console.warn(`[google-calendar] GOOGLE_CALENDAR_API_KEY not set — skipping ${calendarName}`);
    return [];
  }

  const now = new Date();
  const future = new Date(now.getTime() + DAYS_AHEAD * 86400 * 1000);
  const timeMin = now.toISOString();
  const timeMax = future.toISOString();

  const url = `${BASE}/${encodeURIComponent(calendarId)}/events?` + new URLSearchParams({
    key: API_KEY,
    timeMin,
    timeMax,
    maxResults: '250',
    singleEvents: 'true',
    orderBy: 'startTime',
  });

  try {
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.text();
      console.error(`[google-calendar] ${calendarName}: ${res.status} ${body.slice(0, 200)}`);
      return [];
    }
    const data = await res.json();
    return (data.items ?? [])
      .map((item: any) => toCalEvent(item, calendarName, calendarSlug, color))
      .filter(Boolean) as CalEvent[];
  } catch (e) {
    console.error(`[google-calendar] ${calendarName}: fetch failed`, e);
    return [];
  }
}

export async function fetchMultipleCalendars(
  calendars: Array<{ id: string; name: string; slug: string; color: string }>,
): Promise<CalEvent[]> {
  const results = await Promise.all(
    calendars.map(c => fetchCalendarEvents(c.id, c.name, c.slug, c.color))
  );
  return results.flat().sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time));
}

// Format date for display: "Sat, Jun 7"
export function formatDisplayDate(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00'); // noon to avoid timezone edge cases
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

// Group events by date
export function groupByDate(events: CalEvent[]): Map<string, CalEvent[]> {
  const map = new Map<string, CalEvent[]>();
  for (const e of events) {
    if (!map.has(e.date)) map.set(e.date, []);
    map.get(e.date)!.push(e);
  }
  return map;
}
