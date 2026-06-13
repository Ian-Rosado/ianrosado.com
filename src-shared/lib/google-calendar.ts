const API_KEY = import.meta.env.GOOGLE_CALENDAR_API_KEY;
const BASE = 'https://www.googleapis.com/calendar/v3/calendars';
const TZ = 'America/Los_Angeles';
const DAYS_AHEAD = 90;

// Today and the horizon, as YYYY-MM-DD strings in Pacific time. Used to clip
// multi-day events so they never render on past days or far beyond the window.
const TODAY_STR = new Date().toLocaleDateString('en-CA', { timeZone: TZ });
function addDaysStr(ymd: string, n: number): string {
  const [y, m, d] = ymd.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}
const HORIZON_STR = addDaysStr(TODAY_STR, DAYS_AHEAD);

export type CostClass = 'free' | 'paid' | 'unknown';

export interface CalEvent {
  id: string;
  title: string;
  date: string;        // YYYY-MM-DD (Pacific)
  time: string;        // h:mm AM/PM, or '' for all-day
  endTime: string;     // h:mm AM/PM, or ''
  sortKey: number;     // minutes since midnight (Pacific) for chronological sort; -1 for all-day
  allDay: boolean;
  location: string;
  cost: string;
  costClass: CostClass; // free | paid | unknown — for filtering
  genres: string[];     // from extendedProperties.shared.genres
  age: string;          // from extendedProperties.shared.age
  neighborhood: string; // from extendedProperties.shared.neighborhood
  tags: string[];       // full tag list from extendedProperties.shared.tags
  url: string;         // source URL (from description line 2)
  googleUrl: string;   // link to Google Calendar event
  calendarName: string;
  calendarSlug: string;
  color: string;
}

// Classify a cost string into a filterable bucket
export function classifyCost(cost: string): CostClass {
  const c = (cost || '').trim().toLowerCase();
  if (!c) return 'unknown';
  // Free signals
  if (/\bfree\b|no cover|\$0\b|donation|pwyc|pay what|by donation/.test(c)) return 'free';
  // Paid signals — any dollar amount > 0
  if (/\$\s?\d/.test(c)) return 'paid';
  return 'unknown';
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

// Minutes since midnight (Pacific) for a timed event's start. Used for
// chronological sorting — the display `time` string ("10:00 AM") can't be
// compared lexically (it would sort after "1:00 PM").
function minutesOfDay(iso: string): number {
  const hhmm = new Date(iso).toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ,
  }); // e.g. "21:00"
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

// Returns one CalEvent per day the event occupies. Single-day events yield a
// one-element array; multi-day all-day events (e.g. festivals) are expanded
// across each day they span, clipped to [today, horizon].
function toCalEvents(
  item: any,
  calendarName: string,
  calendarSlug: string,
  color: string,
): CalEvent[] {
  const title = item.summary?.trim();
  if (!title) return [];

  const startRaw = item.start?.dateTime ?? item.start?.date ?? '';
  const endRaw   = item.end?.dateTime   ?? item.end?.date   ?? '';
  if (!startRaw) return [];

  const allDay = !item.start?.dateTime;
  const time    = allDay ? '' : formatTime(startRaw);
  const endTime = allDay ? '' : (endRaw ? formatTime(endRaw) : '');
  const sortKey = allDay ? -1 : minutesOfDay(startRaw);

  const { cost, url } = parseDescription(item.description ?? '');

  // Facets written by the add-to-calendar script via extendedProperties.shared
  const shared = item.extendedProperties?.shared ?? {};
  const splitList = (s?: string) =>
    (s ?? '').split(',').map((x: string) => x.trim()).filter(Boolean);
  const genres = splitList(shared.genres);
  const tags = splitList(shared.tags);
  const age = (shared.age ?? '').trim();
  const neighborhood = (shared.neighborhood ?? '').trim();
  // Prefer the stored cost class; fall back to parsing the cost text
  const costClass = (shared.cost as CostClass) || classifyCost(cost);

  // Determine the inclusive list of day-strings this event covers.
  // For all-day events Google's end.date is EXCLUSIVE, so the last day is end-1.
  let days: string[];
  if (allDay) {
    const startDay = startRaw; // already YYYY-MM-DD
    const endExclusive = endRaw || addDaysStr(startDay, 1);
    const lastInclusive = addDaysStr(endExclusive, -1);
    // Clip to [today, horizon]
    const from = startDay < TODAY_STR ? TODAY_STR : startDay;
    const to = lastInclusive > HORIZON_STR ? HORIZON_STR : lastInclusive;
    days = [];
    for (let d = from; d <= to; d = addDaysStr(d, 1)) days.push(d);
  } else {
    // Timed events: render on their start day only.
    days = [formatDate(startRaw)];
  }

  const multiDay = days.length > 1;

  return days.map((date, i) => ({
    id: multiDay ? `${item.id}_${date}` : item.id,
    title,
    date,
    time,
    endTime,
    sortKey,
    allDay,
    location: item.location?.trim() ?? '',
    cost,
    costClass,
    genres,
    age,
    neighborhood,
    tags,
    url,
    googleUrl: item.htmlLink ?? '',
    calendarName,
    calendarSlug,
    color,
  }));
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
    maxResults: '2500',
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
      .flatMap((item: any) => toCalEvents(item, calendarName, calendarSlug, color)) as CalEvent[];
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
  return results.flat().sort((a, b) => a.date.localeCompare(b.date) || a.sortKey - b.sortKey);
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
