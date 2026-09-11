-- Run this once in the Supabase SQL Editor (Dashboard -> SQL Editor ->
-- New query -> paste -> Run). Creates every table the platform uses.
-- The app connects with the service_role key (server-side only), so no
-- row-level-security policies are needed for this internal tool.

create table if not exists notes (
  id bigint generated always as identity primary key,
  date text, account text, author text,
  category text, impact text, note text
);

create table if not exists kb_articles (
  id bigint generated always as identity primary key,
  account text, title text, content text,
  author text, impact text, updated_at text
);

create table if not exists custom_accounts (
  id bigint generated always as identity primary key,
  account text, ticker text, industry text, sub_industry text,
  ai_hiring int, ai_announce int, cloud int, global_reach int,
  data_centre int, added_by text, created_at text, rationale text
);

create table if not exists news_signals (
  id bigint generated always as identity primary key,
  account text, news_score int, article_count int,
  news_adj float, last_refreshed text
);

create table if not exists headlines (
  id bigint generated always as identity primary key,
  account text, published text, source text, title text, link text
);

create table if not exists transcript_feedback (
  id bigint generated always as identity primary key,
  date text, account text, predicted text, corrected text, excerpt text
);

create table if not exists learned_keywords (
  id bigint generated always as identity primary key,
  category text, term text, added_by text, date text
);

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
