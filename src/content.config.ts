import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const recipes = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/recipes' }),
  schema: z.object({
    title: z.string(),
    date: z.date(),
    description: z.string(),
    coverImage: z.string().optional(),
    tags: z.array(z.string()).default([]),
    ingredients: z.array(z.string()),
    equipment: z.array(z.string()).default([]),
  }),
});

export const collections = { recipes };
