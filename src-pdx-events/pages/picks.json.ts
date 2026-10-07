// The current week's and weekend's picks as JSON, for the WebMCP
// get_weekly_picks tool (src-pdx-events/scripts/webmcp.ts).
import { currentWeek, currentWeekend, rangeLabel, type Roundup } from '../lib/picks';

const SITE = 'https://www.pdx-events.com';

function roundup(r: Roundup | undefined) {
  if (!r) return null;
  return {
    title: r.type === 'week' ? `Events of the Week: ${rangeLabel(r)}` : `Plan Your Weekend: ${rangeLabel(r)}`,
    start: r.start,
    end: r.end,
    url: `${SITE}/picks/${r.id}/`,
    picks: r.picks.map((p) => ({
      date: p.date,
      ...(p.endDate ? { end_date: p.endDate } : {}),
      time: p.time,
      ...(p.slot ? { slot: p.slot } : {}),
      category: p.category,
      name: p.name,
      description: p.description,
      venue: p.venue,
      details: p.details,
      free: p.free,
    })),
  };
}

export function GET() {
  return new Response(JSON.stringify({ week: roundup(currentWeek()), weekend: roundup(currentWeekend()) }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
