import { neon } from '@neondatabase/serverless';

// DATABASE_URL is required at runtime, not at build time.
// Set it in web/.env.local (local dev) or Vercel environment variables (prod).
export function getDb() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL is not set.');
  return neon(url);
}
