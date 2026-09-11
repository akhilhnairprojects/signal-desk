-- Row-level security for the public demo.
--
-- Run this AFTER supabase_schema.sql (and upgrade_v23.sql). It is idempotent:
-- safe to re-run.
--
-- WHY THIS FILE EXISTS
-- Supabase grants the `anon` role access to tables in the public schema, and
-- tables created by plain `create table` have RLS switched off. That
-- combination means anyone holding the anon key - which ships to the browser
-- in most Supabase apps - can read, write and delete every row, with no
-- policy anywhere saying so. Enabling RLS flips the default to deny, and the
-- policies below then state the access explicitly.
--
-- WHAT THIS GRANTS
-- Full CRUD to anon. That is deliberate, not laziness: this is a public demo
-- and the app genuinely needs delete. The inline notes editor
-- (store.replace_table), the KB upsert (store.replace_where) and the nightly
-- news refresh (store.replace_accounts) are all delete-then-insert. Blocking
-- delete would break them.
--
-- The exposure is that a visitor could clear the demo data. That is
-- recoverable: data/ in the repo holds a CSV mirror of every table, and the
-- weekly sync re-mirrors them.
--
-- TO LOCK IT DOWN INSTEAD
-- If you would rather the public demo be read-mostly, run this file, then
-- drop the write policies on the tables you want frozen, e.g.
--     drop policy "demo insert" on outcomes;
--     drop policy "demo update" on outcomes;
--     drop policy "demo delete" on outcomes;
-- and give GitHub Actions a service_role key so the collectors keep working.
-- Never put a service_role key in the Streamlit app's secrets.

do $$
declare
  t text;
  tables text[] := array[
    'notes', 'kb_articles', 'custom_accounts', 'news_signals', 'headlines',
    'transcript_feedback', 'learned_keywords', 'measured_signals',
    'competitor_headlines', 'outcomes'
  ];
begin
  foreach t in array tables loop
    if to_regclass('public.' || t) is null then
      raise notice 'skipping %, table not found - run supabase_schema.sql first', t;
      continue;
    end if;

    execute format('alter table public.%I enable row level security', t);

    execute format(
      'drop policy if exists "demo read" on public.%I', t);
    execute format(
      'create policy "demo read" on public.%I for select to anon, authenticated using (true)', t);

    execute format(
      'drop policy if exists "demo insert" on public.%I', t);
    execute format(
      'create policy "demo insert" on public.%I for insert to anon, authenticated with check (true)', t);

    execute format(
      'drop policy if exists "demo update" on public.%I', t);
    execute format(
      'create policy "demo update" on public.%I for update to anon, authenticated using (true) with check (true)', t);

    execute format(
      'drop policy if exists "demo delete" on public.%I', t);
    execute format(
      'create policy "demo delete" on public.%I for delete to anon, authenticated using (true)', t);

    raise notice 'RLS enabled with demo policies on %', t;
  end loop;
end $$;

-- Verify: every table should report rowsecurity = true and 4 policies.
select c.relname as table_name,
       c.relrowsecurity as rls_enabled,
       count(p.polname) as policies
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_policy p on p.polrelid = c.oid
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname in (
    'notes', 'kb_articles', 'custom_accounts', 'news_signals', 'headlines',
    'transcript_feedback', 'learned_keywords', 'measured_signals',
    'competitor_headlines', 'outcomes')
group by c.relname, c.relrowsecurity
order by c.relname;
