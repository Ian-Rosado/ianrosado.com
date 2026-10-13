// Browser-side "is this event still worth listing?" check. Pages are rebuilt
// only every few hours, so they can't know the visitor's time: lists call
// this on load to drop events that are already over. Pacific time.
//
//   - timed event with an end time: shown until it ends (an evening show
//     that runs past midnight stays up the next morning until it's over)
//   - timed event with no end time: shown until GRACE_MIN after it starts
//   - all-day event: shown on its day(s)
//   - anything on a later day: shown

const TZ = 'America/Los_Angeles';
const GRACE_MIN = 60;

export type IsUpcoming = (date: string, time: string, endMin: number) => boolean;

// "7:30 PM" → minutes since midnight; -1 for "all day"
function startMin(time: string): number {
  const m = time.match(/(\d{1,2}):(\d{2})\s*([AP])M/i);
  if (!m) return -1;
  return ((Number(m[1]) % 12) + (m[3].toUpperCase() === 'P' ? 12 : 0)) * 60 + Number(m[2]);
}

export function makeIsUpcoming(now = new Date()): IsUpcoming {
  const today = now.toLocaleDateString('en-CA', { timeZone: TZ }); // YYYY-MM-DD
  const [h, m] = now
    .toLocaleTimeString('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .split(':').map(Number);
  const nowMin = h * 60 + m;

  return (date, time, endMin) => {
    if (date > today) return true;
    // Days between the event's date and today (0 = today)
    const daysAgo = Math.round((Date.parse(today) - Date.parse(date)) / 86400000);
    const start = startMin(time);
    if (start < 0) return daysAgo === 0;                       // all-day
    if (endMin >= 0) return endMin - 1440 * daysAgo > nowMin;  // until it ends
    return daysAgo === 0 && start >= nowMin - GRACE_MIN;       // no end time
  };
}

// Prune server-rendered rows: `.date-group[data-date]` sections of `li.er`
// rows (time in `.er-time`, end in `data-end`). Empty sections are removed.
// Returns how many rows are left.
export function pruneRenderedRows(root: ParentNode, isUpcoming: IsUpcoming): number {
  let left = 0;
  root.querySelectorAll<HTMLElement>('.date-group').forEach((section) => {
    const date = section.dataset.date ?? '';
    section.querySelectorAll<HTMLElement>('li.er').forEach((row) => {
      const time = row.querySelector('.er-time')?.textContent ?? '';
      const end = row.dataset.end ? Number(row.dataset.end) : -1;
      if (isUpcoming(date, time, end)) left++;
      else row.remove();
    });
    if (!section.querySelector('li.er')) section.remove();
  });
  return left;
}
