// WebMCP (https://webmachinelearning.github.io/webmcp/): tools an AI agent in
// the browser can call instead of clicking through the page. Read-only; data
// comes from the site's own /events.json and /picks.json. Loaded by the
// Layout only when the browser exposes a model context (Chrome 146+ preview),
// so regular visitors never download it. Results link back to pdx-events.com.

const SITE = 'https://www.pdx-events.com';
const MAP_PREFIX = 'https://www.google.com/maps/search/?api=1&query=';

const CATEGORIES = ['events', 'live-music', 'comedy', 'karaoke', 'farmers-markets', 'sports', 'trivia', 'pedalpalooza'] as const;
// Category → its landing page, for "see more" links
const CATEGORY_PAGE: Record<string, string> = {
  'live-music': '/live-music/', comedy: '/comedy/', karaoke: '/karaoke/', 'farmers-markets': '/farmers-markets/',
  sports: '/sports/', trivia: '/trivia/', pedalpalooza: '/bike-rides/',
};

// /events.json shape: see src-shared/lib/events-payload.ts
type EventTuple = [number, string, string, string, string, string, string, string];
interface EventsPayload {
  cats: [string, string, string][];
  days: [string, EventTuple[]][];
}

let eventsPromise: Promise<EventsPayload> | null = null;
const loadEvents = () => (eventsPromise ??= fetch('/events.json').then((r) => r.json()));

// MCP CallToolResult
const result = (data: unknown) => ({ content: [{ type: 'text', text: JSON.stringify(data) }] });

const DATE = { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' };

const tools = [
  {
    name: 'search_events',
    description:
      'Search upcoming events in Portland, Oregon (next 90 days) on PDX Events: festivals, live music, comedy, ' +
      'karaoke, farmers markets, sports, trivia nights and group bike rides. Filter by keyword, category, date ' +
      'range and free-only. Returns date, time, title, location, cost and a link for each event, sorted by date.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Keyword(s) matched against the event title and location, e.g. "jazz" or "Alberta".' },
        category: { type: 'string', enum: CATEGORIES, description: 'Only events of this kind. "events" is general events/festivals; "pedalpalooza" is group bike rides.' },
        start_date: { ...DATE, description: 'First day to include (YYYY-MM-DD, Pacific time). Defaults to today.' },
        end_date: { ...DATE, description: 'Last day to include (YYYY-MM-DD). Defaults to the end of the 90-day window.' },
        free_only: { type: 'boolean', description: 'Only events known to be free.' },
        limit: { type: 'integer', minimum: 1, maximum: 100, description: 'Maximum events to return (default 25).' },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, untrustedContentHint: true },
    async execute(input: {
      query?: string; category?: string; start_date?: string; end_date?: string; free_only?: boolean; limit?: number;
    }) {
      const data = await loadEvents();
      const words = (input.query ?? '').toLowerCase().split(/\s+/).filter(Boolean);
      const limit = Math.min(Math.max(input.limit ?? 25, 1), 100);
      const matches = [];
      for (const [date, tuples] of data.days) {
        if (input.start_date && date < input.start_date) continue;
        if (input.end_date && date > input.end_date) break;
        for (const [cat, time, title, location, mapQuery, cost, costClass, link] of tuples) {
          const category = data.cats[cat][0];
          if (input.category && category !== input.category) continue;
          if (input.free_only && costClass !== 'free') continue;
          const hay = `${title} ${location}`.toLowerCase();
          if (!words.every((w) => hay.includes(w))) continue;
          matches.push({
            date,
            time,
            title,
            category,
            location,
            cost: costClass === 'free' ? 'Free' : cost || 'unknown',
            ...(link ? { url: link } : {}),
            ...(mapQuery ? { map: MAP_PREFIX + mapQuery } : {}),
          });
        }
      }
      const page = input.category ? CATEGORY_PAGE[input.category] : input.free_only ? '/free/' : '/';
      return result({
        total_matches: matches.length,
        returned: Math.min(matches.length, limit),
        events: matches.slice(0, limit),
        browse: `${SITE}${page ?? '/'}`,
      });
    },
  },
  {
    name: 'get_weekly_picks',
    description:
      "Get PDX Events' hand-picked highlights for Portland, Oregon: this week's Events of the Week (a daytime and " +
      'an evening pick for each day) and, when there is one, the upcoming Plan Your Weekend list. Each pick has ' +
      'a short description of why it is worth going to.',
    inputSchema: {
      type: 'object',
      properties: {
        which: { type: 'string', enum: ['week', 'weekend', 'both'], description: 'Which list to return (default "both").' },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(input: { which?: 'week' | 'weekend' | 'both' }) {
      const data = await fetch('/picks.json').then((r) => r.json());
      const which = input.which ?? 'both';
      return result({
        ...(which !== 'weekend' ? { week: data.week } : {}),
        ...(which !== 'week' ? { weekend: data.weekend } : {}),
        all_picks: `${SITE}/picks/`,
      });
    },
  },
];

export async function registerTools() {
  // document.modelContext is the current surface; navigator is Chrome 146–149
  const modelContext = (document as any).modelContext ?? (navigator as any).modelContext;
  for (const tool of tools) {
    try {
      await modelContext?.registerTool(tool);
    } catch (err) {
      console.warn(`[webmcp] couldn't register ${tool.name}`, err);
    }
  }
}
