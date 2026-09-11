-- If your Supabase project already exists, run ONLY this file in the SQL
-- Editor to add the three v2.3 tables. (New projects: run the full
-- supabase_schema.sql instead - it now includes these.)

-- v2.3 additions ------------------------------------------------------------

create table if not exists measured_signals (
  id bigint generated always as identity primary key,
  account text, signal text, value int, source text, collected_at text
);

create table if not exists competitor_headlines (
  id bigint generated always as identity primary key,
  account text, published text, source text, title text, link text,
  theme text
);

create table if not exists outcomes (
  id bigint generated always as identity primary key,
  date text, account text, outcome text, amount text, note text,
  logged_by text
);
