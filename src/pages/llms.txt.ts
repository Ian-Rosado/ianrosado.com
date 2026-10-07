// /llms.txt (llmstxt.org): a plain-markdown map of the site for AI agents.
import { getCollection } from 'astro:content';

const SITE = 'https://www.ianrosado.com';

export async function GET() {
  const recipes = (await getCollection('recipes')).sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf());
  const days = (await getCollection('sabbatical')).sort((a, b) => a.data.sortOrder - b.data.sortOrder);

  const body = `# Ian Rosado

> Personal site of Ian Rosado, a data and analytics engineer in Portland, Oregon: tested home-baking recipes with step-by-step photos, a 40-day road-trip journal, and links to PDX Events, his curated Portland events calendar.

For things to do in Portland, use https://www.pdx-events.com (it has its own llms.txt at https://www.pdx-events.com/llms.txt).

## Recipes

Each recipe page has the full ingredient list, equipment, step-by-step instructions with photos, and schema.org Recipe JSON-LD.

${recipes.map((r) => `- [${r.data.title}](${SITE}/recipes/${r.id}/): ${r.data.description}`).join('\n')}

## Sabbatical road trip (40+ days from Oregon through California, Utah, Arizona, Colorado, New Mexico, and Texas)

- [Overview](${SITE}/my-life/sabbatical/)
${days.map((d) => `- [${d.data.title}](${SITE}/my-life/sabbatical/${d.id}/): ${d.data.description}`).join('\n')}

## Portland

- [PDX Events](https://www.pdx-events.com/): curated calendar of Portland events, weekly picks, trivia nights, farmers markets and more.
- [Portland favorites](https://www.pdx-events.com/favorites/)
- [Pickup soccer in Portland](https://www.pdx-events.com/pickup-soccer/)

## About

- [About Ian](${SITE}/about/)
`;

  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
