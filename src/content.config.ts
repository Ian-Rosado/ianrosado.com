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
    prepTime: z.string().optional(),
    cookTime: z.string().optional(),
    totalTime: z.string().optional(),
    recipeYield: z.string().optional(),
    recipeCuisine: z.string().optional(),
    recipeCategory: z.string().optional(),
  }),
});

const sabbatical = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/sabbatical' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    sortOrder: z.number(),
    photoSource: z.string().default('sabbatical'),
    layout: z.enum(['gallery', 'inline', 'carousel']).default('gallery'),
    mapId: z.string().optional(),
    coverPhoto: z.string().default('photo-01.jpg'),
    wideContent: z.boolean().default(false),
  }),
});

export const collections = { recipes, sabbatical };
