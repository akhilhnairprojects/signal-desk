# Playbook: from a blank laptop to a live, self-updating platform

This guide assumes you have never used Python, Git, GitHub, or Streamlit.
Follow it top to bottom. First-time setup: roughly 2 hours, most of it
waiting for installers and downloads. Everything happens on **your own
laptop** (not the VDI). Once deployed, the live app and every automation
trigger work from any browser — including the VDI — because they are just
websites.

---

## Part 1 — One-time laptop setup (~30 min)

1. **Python 3.11+** from python.org → during install, **tick "Add
   python.exe to PATH"** (the single most missed checkbox in computing).
2. **VS Code** from code.visualstudio.com, then install its **Python**
   extension (Extensions icon → search Python → Install).
3. **A GitHub account** at github.com (free). Remember which email you
   used — everything else signs in through it.

## Part 2 — Get the project running locally (~25 min)

1. Put the project folder somewhere simple (e.g. Desktop) and open it in
   VS Code (**File → Open Folder**).
2. Open a terminal (**Terminal → New Terminal**) and create a virtual
   environment: `python -m venv .venv`
3. Activate it: `.venv\Scripts\activate` — the prompt gains a `(.venv)`
   prefix. If PowerShell refuses ("running scripts is disabled"), run
   `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`, answer Y, and
   retry.
4. Install everything: `pip install -r requirements.txt`
   > **This install is large (~1 GB) and takes 5–15 minutes** — the
   > transcript analyzer runs a PyTorch language model. One-time per
   > machine; if it fails mid-download, run the same command again.
5. Build the dataset: `python scripts/run_pipeline.py` — expect
   "Scored 160 accounts across 9 industries."
6. Launch: `streamlit run streamlit_app.py` — the app opens in your
   browser at localhost:8501. Ctrl+C in the terminal stops it.

## Part 3 — Put the project on GitHub (~15 min)

1. In VS Code: **Source Control icon → Initialize Repository**.
2. Type a message ("Initial platform") → **Commit** → **Publish Branch**
   → choose **public** (Streamlit's free hosting needs it) → sign in to
   GitHub when prompted.
3. Confirm on github.com that your repo shows `streamlit_app.py`,
   `requirements.txt`, `src/`, `pages/`, `data/` **at the top level** —
   not nested inside another folder.

Never commit two things: the `.venv` folder and
`.streamlit/secrets.toml`. Both are already in `.gitignore`; leave that
protection alone.

## Part 4 — The persistent database (Supabase) (~15 min)

Streamlit Cloud's file system is wiped on every restart; the database is
what makes notes, articles, added companies, outcomes, and learned
keywords permanent.

1. **supabase.com → Start your project** → sign in **with GitHub**. New
   project: name `account-intelligence`, generate & save the DB password,
   pick a US-East region, wait ~2 min.
2. **SQL Editor → New query** → paste ALL of `setup/supabase_schema.sql`
   → **Run**. Table Editor should show **10 tables** (notes, kb_articles,
   custom_accounts, news_signals, headlines, transcript_feedback,
   learned_keywords, measured_signals, competitor_headlines, outcomes).
   *Already had a Supabase project from an earlier version?* Run only
   `setup/upgrade_v23.sql` instead — it adds the last three.
3. **Project Settings (gear) → API** → copy the **Project URL** and the
   **`anon` public key**.
   ⚠️ Use `anon`, **not** `service_role`. The service-role key bypasses
   row-level security completely, so a leak exposes the whole database.
   `anon` plus the RLS policies in `docs/deployment.md` is enough for
   everything this app does. Either key goes only into the private secret
   boxes below — never into code, a commit, or a chat window.
4. Put both values in **three places**:
   - **Laptop:** copy `.streamlit/secrets.toml.example` →
     `secrets.toml` (same folder), fill in url and key.
   - **Streamlit Cloud** (after Part 5): app → Settings → **Secrets** →
     paste the same three lines.
   - **GitHub Actions:** repo → Settings → Secrets and variables →
     Actions → new secrets `SUPABASE_URL` and `SUPABASE_KEY`.
5. **Verify:** run the app; under the home-page KPIs it must read
   **Storage: Persistent database (Supabase)**. Add a test note → it
   appears in Supabase's Table Editor.

> Free Supabase projects pause after ~7 idle days; the nightly job's
> writes keep yours awake. If it ever pauses, the dashboard shows a
> one-click **Restore**.

## Part 5 — Deploy to Streamlit Cloud (~15 min)

1. **share.streamlit.io** → sign in with GitHub → **Create app**.
2. Repository: `your-username/account-intelligence` · Branch: `main` ·
   Main file: `streamlit_app.py`.
3. **Advanced settings → Python version → 3.11.** Do not skip this: the
   platform's newest default Python segfaults under PyTorch. (The
   matching guard, `fileWatcherType = "none"`, already ships in
   `.streamlit/config.toml` — leave it.)
4. **Deploy.** First build takes 5–10 minutes (installing PyTorch); watch
   the log until "Your app is live".
5. Add the Supabase secrets (Part 4.4, place 2). The app reboots itself.
6. If the app ever shows "Oh no" instead of loading: **Manage app**
   (bottom-right) opens the log — the real error is in the last ~20
   lines, and the Troubleshooting table below covers the usual suspects.

## Part 6 — Activate the intelligence feeds (~15 min, mostly optional)

- **SEC filings (required for measured signals):** in `src/config.py`,
  set `EDGAR_CONTACT` to **your real email** — SEC's fair-use policy
  requires an identifying User-Agent, and the collector refuses to run
  until it's set. Commit the change.
- **AI job postings (optional, grows over time):** add rows to
  `data/measured/hiring_sources.csv` (`account,ats,board_token`) for
  companies whose careers pages live at `boards.greenhouse.io/TOKEN` or
  `jobs.lever.co/TOKEN` — e.g. `Stripe,greenhouse,stripe`. Unmapped
  accounts simply keep their estimates. Most mega-enterprises use
  Workday, so partial coverage is expected and fine.
- **Digest & alerts (optional):** repo → Settings → Secrets → Actions.
  Email: `SMTP_USER` (a Gmail address), `SMTP_PASSWORD` (an **app
  password**: Google Account → Security → 2-Step Verification → App
  passwords), `DIGEST_TO` (recipients, comma-separated). Teams:
  `TEAMS_WEBHOOK_URL` (channel → ⋯ → Connectors → Incoming Webhook).
  Configure either, both, or neither — unconfigured channels are skipped
  silently.

## Part 7 — How the platform runs itself

Three GitHub Actions run on GitHub's servers — laptop off, VDI locked,
doesn't matter:

- **Nightly news collection** (~1–2 AM ET): fresh AI headlines for every
  account *and* every competitor, full rescore, tier-change alerts if
  channels are configured, commit → the app redeploys with morning-fresh
  data.
- **Weekly dashboard sync** (Friday nights): SEC-filings and job-posting
  measurement, the week's digest for the home page (and inbox/Teams if
  configured), and every database table mirrored into `data/` as a
  versioned backup.
- **Refresh** (on change): any commit touching `data/` or `src/` re-runs
  the pipeline.

**Trigger any of them from any browser — including the VDI:** repo →
**Actions** tab → pick the workflow → **Run workflow**. That's your
"update everything now" button. GitHub pauses schedules after ~60 quiet
days (one-click re-enable banner on the Actions tab); the nightly job's
own commits normally keep the clock fresh.

## Part 8 — Everyday workflows

**Read the room each morning.** Overview shows the portfolio, the weekly
digest, any 🔔 tier changes since the last refresh, and whether scores
run on configured or learned weights. Click a tier bar to cross-filter
the page; click again to clear.

**Capture what you learn.** Knowledge Base: quick field notes (±2 pts,
whole log editable inline like a spreadsheet — click, fix, Save) and KB
articles (±1 pt, edited in place). Both decay after six months so old
intel fades; each item shows its current weight.

**Add a company on the fly.** Add a Company → name + industry →
Research: the platform builds the profile from the industry baseline plus
the company's news, shows the full rationale and evidence, and adds it on
your confirm — first-class from then on.

**Work an account.** Explorer: profile, score-breakdown waterfall,
📐 measured-signal provenance, deduplicated similar accounts, 2–4-way
comparison. Log every **engagement outcome** (Won / Engaged / No
Response / Lost) in the profile's expander — that's the training data.

**Let the model graduate.** Once ≥40 outcomes with ≥10 per class exist,
run `python scripts/train_weights.py`: the weights are learned from your
results, the Overview labels the change, and deleting
`results/learned_weights.json` reverts instantly.

**Mind the competition.** Competitive Intel: the theme matrix shows where
each rival is loudest; pick one for an auto-generated battlecard
(downloadable). Counter-lines live in `COUNTER_PLAYS` in `src/config.py`
— sharpen them as messaging evolves.

**Analyse calls.** Transcript Analyzer: paste a transcript → tone, pain
points with evidence, positioning plays, and numbered next steps; save
the summary to the account; teach it any phrase it missed (applies
immediately).

**Highlight a segment anywhere.** Click a dot on the Segments map or use
the Highlight selector (Segments page / Explorer sidebar): that segment
stays emphasised across the map and every table until you clear it.

## Part 9 — Troubleshooting

| Symptom | Fix |
|---|---|
| PowerShell: "running scripts is disabled" | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`, answer Y, reopen terminal. |
| `pip` or `python` not recognised | Python wasn't added to PATH — reinstall with the checkbox ticked. |
| Deployed app shows "Oh no" / segfault in the log | Recreate the app with **Python 3.11** (Advanced settings) and keep `fileWatcherType = "none"` in `.streamlit/config.toml`. |
| Home page says "Storage: Local CSV files" after Supabase setup | A secret is missing/typo'd in that environment: local `secrets.toml`, Cloud Settings → Secrets, or Actions secrets. Confirm you used the **`anon`** key and that RLS policies exist for the table being read. |
| Transcript page says "VADER (lexicon fallback)" | **Expected.** `torch`/`transformers` are deliberately not deployment dependencies — see `docs/deployment.md`. Install them locally to use the transformer instead. |
| Supabase says project paused | ~7 idle days. Click **Restore**; nothing is lost. |
| Measured collector prints "Set EDGAR_CONTACT..." | Do exactly that (Part 6) and rerun. |
| Competitive Intel says no headlines yet | Run `python scripts/collect_competitor_news.py --limit 3` or trigger the nightly workflow. |
| `train_weights.py` says "Not enough signal yet" | Working as designed — keep logging outcomes until ≥40 with ≥10 per class. |
| Digest/alerts never arrive | Channel secrets unset or Gmail password isn't an **app password**; the workflow log says which. |
| Scheduled workflows stopped | ~60 quiet days pauses them; click the re-enable banner on the Actions tab. |
| Deployed app shows old data | Hard-refresh (Ctrl+Shift+R); if still stale, check the latest Action run committed. |

## Part 10 — Suggested presentation flow (~12 min demo)

1. **The problem (1 min):** static account lists go stale the day they're
   made; reps need a ranked, current, explainable call list.
2. **Overview:** the portfolio, the weekly digest, storage + weights
   provenance — then **click the Tier 1 bar** and watch the page
   cross-filter live.
3. **Explorer:** open an account — the score-breakdown waterfall (the
   methodology, visualised), 📐 measured signals, similar accounts, a
   2-way comparison; **log an outcome** and explain the learning loop.
4. **Add a Company:** the showstopper — research a real company live,
   show the rationale and evidence, add it, reopen it fully scored.
5. **Segments:** click a dot → the segment highlights here, then flip to
   Explorer and show it followed you; flip to the density view for the
   outliers.
6. **News Monitor:** click a row → live headlines, no button; open the
   Actions tab in another window: the nightly job that does this alone.
7. **Competitive Intel:** the messaging matrix, then download a
   battlecard live.
8. **Transcript Analyzer:** the sample call → tone, evidence, next
   steps; teach it a keyword and rerun.
9. **Close (1 min):** everything typed persists, everything measured is
   sourced, everything scheduled is visible in the repo history — and
   the model earns its weights from real outcomes.
