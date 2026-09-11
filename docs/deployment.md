# Deploying for free

The whole stack runs on free tiers with no card on file: **Streamlit Community
Cloud** for the app, **Supabase** for persistence, **GitHub Actions** for the
nightly and weekly collectors.

Total setup time is about 40 minutes, most of it waiting.

---

## Why this stack

**Streamlit Community Cloud** is the right host because Streamlit needs a
long-running process holding a websocket to each browser session.

**Vercel cannot host this.** Vercel is serverless — functions are invoked per
request and torn down, with a 250MB unzipped bundle limit. There is no process
to hold Streamlit's session state. Vercel becomes the right answer only after
the migration to a Next.js front end (see `notes/roadmap-native-app.md`).

Render's free tier would technically work but sleeps after 15 minutes of
inactivity and takes ~50 seconds to wake — a bad first impression when someone
clicks a link from a CV.

### The dependency that decides everything

`torch` + `transformers` is roughly 800MB and will exhaust Streamlit Cloud's
build resources. They are **deliberately not in `requirements.txt`**.

`src/transcript.py` imports `transformers` lazily inside a `try/except` and
falls back to VADER, a lexicon sentiment model that installs in seconds. The
app names the active engine under the results, so nothing is misrepresented.

To use the transformer locally:

```bash
pip install torch transformers --extra-index-url https://download.pytorch.org/whl/cpu
```

Then set `TRANSCRIPT_ENGINE = "transformer"` in `src/config.py`.

---

## Step 1 — Push to GitHub (~10 min)

The app runs with **zero secrets configured** — `src/store.py` falls back to the
committed CSVs. Deploy it this way first and confirm it works before adding a
database.

```bash
cd account-intelligence
git init
git add .
git commit -m "Account intelligence platform"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Two things must be true before you push:

- `data/raw/accounts.xlsx` **is committed**. `src/ingest.py` raises
  `FileNotFoundError` without it, because `config.DATA_URL` is empty.
- `.streamlit/secrets.toml` **is not** committed. `.gitignore` already covers it.

## Step 2 — Deploy the app (~10 min)

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **New app** → pick the repo, branch `main`, main file `streamlit_app.py`.
3. Under **Advanced settings**, set Python version to **3.12**.
4. Deploy. The first build takes 3–5 minutes.

The app is now live at `https://<something>.streamlit.app` and redeploys on
every push to `main`. Edits made in the app are written to the container
filesystem and are lost when it restarts — Step 3 fixes that.

## Step 3 — Persistence with Supabase (~15 min)

1. Create a free project at <https://supabase.com>. Save the database password.
2. **SQL Editor** → run `setup/supabase_schema.sql`, then `setup/upgrade_v23.sql`.
3. **Project Settings → API** and copy the Project URL and the **`anon` public**
   key.

> **Use the `anon` key, never `service_role`.** The service-role key bypasses
> row-level security entirely. In a public Streamlit app the secrets are
> server-side, but the blast radius of a leak is the whole database, and there
> is no reason to take it — `anon` plus the policies below is enough.

4. Enable RLS on every table and add policies. Public read, insert and update
   suit a live demo; keep delete restricted:

```sql
alter table notes enable row level security;

create policy "public read"   on notes for select using (true);
create policy "public insert" on notes for insert with check (true);
create policy "public update" on notes for update using (true);
-- deliberately no delete policy
```

Repeat for `kb_articles`, `custom_accounts`, `outcomes`,
`transcript_feedback`, `learned_keywords`, `news_signals`, `headlines`,
`measured_signals`, `competitor_headlines`.

5. In Streamlit Cloud: **⋮ → Settings → Secrets**, paste, and save:

```toml
[supabase]
url = "https://xxxxxxxx.supabase.co"
key = "eyJhbGciOi..."
```

The app restarts automatically. The Overview caption should now read
**"Persistent database (Supabase)"** instead of "Local CSV files".

If a write ever fails, the app shows a "Saved locally, but the database
rejected the write" warning rather than reporting a false success.

## Step 4 — Keep the data fresh (~5 min)

The workflows in `.github/workflows/` collect news nightly and measured signals
weekly, then commit the refreshed CSVs — which triggers a redeploy.

In the repo: **Settings → Secrets and variables → Actions**, add
`SUPABASE_URL` and `SUPABASE_KEY` (`src/store.py` reads these from the
environment in CI).

Optional digest delivery: `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO`, and/or
`TEAMS_WEBHOOK_URL`. Absent, `scripts/send_digest.py` skips silently.

Before the first run, set a real `EDGAR_CONTACT` in `src/config.py` — SEC EDGAR
requires a contact address in the User-Agent and
`scripts/collect_measured.py` refuses to run with the placeholder.

Trigger a run by hand from the **Actions** tab to confirm the workflows are
wired up.

---

## Verification

Work through this in order; each step isolates a different failure.

1. **No secrets** — load the app before adding Supabase. All 8 pages render,
   Overview says "Local CSV files". This proves the CSV fallback works and the
   workbook is committed.
2. **With Supabase** — Overview says "Persistent database (Supabase)".
3. **Persistence** — add a note on the Knowledge Base page, then **⋮ → Reboot
   app**. The note survives. This is the one thing that cannot be faked and the
   one worth demonstrating.
4. **Cold start** — open the app in a private window. First load runs the
   pipeline (K-Means, UMAP, nearest-neighbours over 160 accounts) and takes
   ~20 seconds; afterwards `@st.cache_data` serves it instantly.
5. **Sentiment engine** — Transcript Analyzer → "Load sample call". It should
   report `Engine: VADER (lexicon fallback)` and produce pain points and next
   steps.
6. **Tests** — `python -m pytest tests/ -q` passes 13 tests.

## Cost

| Service | Tier | Limit that matters |
|---|---|---|
| Streamlit Community Cloud | Free | Public repos, 1GB per app |
| Supabase | Free | 500MB database, pauses after 7 days idle |
| GitHub Actions | Free | 2,000 min/month on public repos |

The Supabase idle pause is the one to watch: an untouched project pauses after
a week and needs a click in the dashboard to resume. The nightly Action
counts as activity, so in practice it stays awake.
