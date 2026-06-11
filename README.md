# Kinetica Docs Change Monitor

Automatically watches a list of Kinetica documentation pages and reports when
they change, so QA test coverage never falls behind the docs.

It runs **3× per day** via GitHub Actions, fetches each page, compares it to the
last stored snapshot, and — if anything changed — commits the diff and opens a
GitHub Issue with a coverage checklist.

## How it works

```
urls.txt  ──►  monitor.py  ──►  fetch + clean text  ──►  diff vs snapshot
                                                              │
                          ┌───────────────────────────────────┤
                          ▼                                   ▼
                 snapshots/ (baselines, committed)    changes/ (diffs this run)
                                                              │
                                                              ▼
                                              GitHub Issue (QA review checklist)
```

- **No change** → run finishes silently, only the `last_checked` timestamp updates.
- **Change** → a `changes/<timestamp>-<page>.md` diff file is committed, and an
  issue titled `📝 Docs changed: N page(s)` is opened with each diff inline and a
  checkbox per page. An unchecked box = an unaddressed doc change.
- **Git history** gives you a full audit trail of every doc change over time.

## Setup (one time)

1. Create a new GitHub repo and add these files:
   ```
   monitor.py
   urls.txt
   requirements.txt
   .github/workflows/monitor.yml
   README.md
   ```
2. Edit **`urls.txt`** — put the real doc pages your team builds tests against,
   one URL per line.
3. Commit and push.
4. In the repo: **Settings → Actions → General → Workflow permissions** →
   select **Read and write permissions** (lets the bot commit snapshots and open issues).
5. Go to the **Actions** tab → select *Kinetica Docs Monitor* → **Run workflow**
   to establish the first baselines.

That's it. From then on it runs on schedule with zero manual effort.

## Daily use

- Watch for issues labeled **`docs-change`**.
- Open the issue, read each diff, update your tests, tick the checkbox.
- Close the issue when all boxes are checked.

## Adjusting

- **Add/remove pages:** edit `urls.txt`.
- **Change frequency:** edit the `cron` line in `.github/workflows/monitor.yml`.
  Current `0 6,12,18 * * *` = 06:00/12:00/18:00 UTC.
- **Reduce false positives:** if a page flags changes from dynamic boilerplate
  (timestamps, version banners), add a regex to `IGNORE_PATTERNS` in `monitor.py`.
- **Reset a baseline:** delete that page's files in `snapshots/` and rerun.

## Notes

- Snapshots store **cleaned text only** (nav/script/style/footer stripped), so
  diffs reflect real content changes, not layout noise.
- If a fetch fails (network/site down), that page is skipped and listed under
  `errors` in the run summary — no false "changed" report.
- Everything is plain files in git; no database or external service needed.
