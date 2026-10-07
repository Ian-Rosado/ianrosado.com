// Calendar metadata comes from the shared config (single source of truth,
// also read by the Python pipeline) — edit src-shared/config/calendars.json,
// not this file.
import config from '../config/calendars.json';

export interface CalendarConfig {
  id: string;
  name: string;
  slug: string;
  description: string;
  color: string; // Tailwind color class
  freeDefault?: boolean;
}

export const CALENDARS: CalendarConfig[] = config.calendars;

// Trivia nights are grouped together on one page
export const TRIVIA_CALENDARS: CalendarConfig[] = config.triviaCalendars;
export const TRIVIA_GROUP: CalendarConfig = config.triviaGroup;
export const PEDALPALOOZA_CALENDAR: CalendarConfig = config.pedalpalooza;

// Slugs whose events are free by default (no cost unless a price is stated).
export const FREE_DEFAULT_SLUGS: Set<string> = new Set(
  [...config.calendars, ...config.triviaCalendars, config.pedalpalooza]
    .filter((c) => c.freeDefault)
    .map((c) => c.slug),
);

// All page-level calendar configs (one entry per page)
export const ALL_CALENDAR_PAGES: CalendarConfig[] = [
  ...CALENDARS,
  TRIVIA_GROUP,
  PEDALPALOOZA_CALENDAR,
];

export const COLOR_MAP: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  orange: { bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-200', dot: 'bg-orange-500' },
  yellow: { bg: 'bg-yellow-50',  text: 'text-yellow-700',  border: 'border-yellow-200', dot: 'bg-yellow-500' },
  purple: { bg: 'bg-purple-50',  text: 'text-purple-700',  border: 'border-purple-200', dot: 'bg-purple-500' },
  pink:   { bg: 'bg-pink-50',    text: 'text-pink-700',    border: 'border-pink-200',   dot: 'bg-pink-500'   },
  green:  { bg: 'bg-green-50',   text: 'text-green-700',   border: 'border-green-200',  dot: 'bg-green-500'  },
  blue:   { bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-200',   dot: 'bg-blue-500'   },
  teal:   { bg: 'bg-teal-50',    text: 'text-teal-700',    border: 'border-teal-200',   dot: 'bg-teal-500'   },
  red:    { bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',    dot: 'bg-red-500'    },
};
