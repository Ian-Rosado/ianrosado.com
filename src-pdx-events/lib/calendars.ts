export interface CalendarConfig {
  id: string;
  name: string;
  slug: string;
  description: string;
  color: string; // Tailwind color class
}

export const CALENDARS: CalendarConfig[] = [
  {
    id: '6218570f10546f6f03748bbd25adcde299bfd55ef4741d8d1520e79653d9c9f6@group.calendar.google.com',
    name: 'Portland Events',
    slug: 'events',
    description: 'Festivals, markets, community events, outdoor activities, film, arts, and one-of-a-kind Portland happenings.',
    color: 'orange',
  },
  {
    id: '34ae96ffcf119eb4dbf6acf86b0886273efeb8a702ed6e9267ef3d24f0e9a1f7@group.calendar.google.com',
    name: 'Portland Live Music',
    slug: 'live-music',
    description: 'Concerts, shows, and live performances across Portland venues.',
    color: 'yellow',
  },
  {
    id: '94a06447d97328f27a5e219c8e01c42be692998a7573738132a4405a739efec4@group.calendar.google.com',
    name: 'Portland Comedy',
    slug: 'comedy',
    description: 'Stand-up, improv, open mics, and comedy shows around Portland.',
    color: 'purple',
  },
  {
    id: 'e911229a59a93265f26cc81a1cbd2c3be4300fad84e935846ddb8fa7909f42fb@group.calendar.google.com',
    name: 'Portland Karaoke',
    slug: 'karaoke',
    description: 'Karaoke nights at bars and venues around Portland.',
    color: 'pink',
  },
  {
    id: '560e859bd2c7b5dfd2262cb6f28389921434606cec955e7ec75f02df9fd2138a@group.calendar.google.com',
    name: 'Portland Farmers Markets',
    slug: 'farmers-markets',
    description: 'Weekly farmers markets across the Portland metro area.',
    color: 'green',
  },
];

// Trivia nights are grouped together on one page
export const TRIVIA_CALENDARS: CalendarConfig[] = [
  {
    id: '561e4a90958248768cba407c23d37f1293e28f3749bc14de503d258fc03a48c7@group.calendar.google.com',
    name: 'Trivia Nights – N/NE',
    slug: 'trivia',
    description: '',
    color: 'blue',
  },
  {
    id: '088af359972350285c1e5bccda5fb38c349d0597d7c795ef3d1c21d7b973e457@group.calendar.google.com',
    name: 'Trivia Nights – NW/SW',
    slug: 'trivia',
    description: '',
    color: 'blue',
  },
  {
    id: '441feafdb38c603cde09cd9a60e4f8ed10be90a21eb26dee01db64d0c8594a88@group.calendar.google.com',
    name: 'Trivia Nights – SE',
    slug: 'trivia',
    description: '',
    color: 'blue',
  },
  {
    id: 'ac0a6fedb05274655f5e68e9ec26c3f9b341866ae0feed97dd703e94f164a0bf@group.calendar.google.com',
    name: 'Trivia Nights – Further Out',
    slug: 'trivia',
    description: '',
    color: 'blue',
  },
];

export const TRIVIA_GROUP: CalendarConfig = {
  id: 'trivia-group',
  name: 'Trivia Nights',
  slug: 'trivia',
  description: 'Weekly pub trivia nights across N/NE, NW/SW, SE Portland, and surrounding areas.',
  color: 'blue',
};

export const PEDALPALOOZA_CALENDAR: CalendarConfig = {
  id: 'd11s65r5vlq540k2aicdm8c7ndrp6dsl@import.calendar.google.com',
  name: 'Pedalpalooza',
  slug: 'pedalpalooza',
  description: 'Shift bike events and Pedalpalooza rides year-round.',
  color: 'teal',
};

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
};
