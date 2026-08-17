# Setup Guide

Step-by-step setup for the Smart ADO Hours Auto-Logger.

---

## 1. Prerequisites

- **Python 3.8+** — check with `python3 --version`
- **pip** — check with `pip --version`
- **Linux with notifications** (optional) — install `notify-send`:
  ```bash
  sudo apt install libnotify-bin
  ```
- An **Azure DevOps account** with access to your project.

---

## 2. Clone and install

```bash
git clone https://github.com/MandalKushagra/ado-hours-autologger.git
cd ado-hours-autologger
pip install -r requirements.txt
```

> Prefer a virtual environment?
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> ```
> If you use a venv, update the cron wrapper to call the venv's python (see step 6 note).

---

## 3. Create an Azure DevOps PAT

1. Go to `https://dev.azure.com/<your-org>/_usersSettings/tokens`
   (for Delhivery: https://dev.azure.com/delhivery/_usersSettings/tokens)
2. Click **New Token**.
3. Name it (e.g. `hours-autologger`).
4. Set an expiry (max 1 year — you'll need to rotate it after).
5. Under **Scopes**, choose **Custom defined**, then enable:
   - **Work Items → Read & Write**
6. Click **Create** and **copy the token now** (you can't see it again).

---

## 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```ini
ADO_PAT=paste_your_token_here
ADO_ORG=delhivery
ADO_PROJECT=GM-WMS
DAILY_BUDGET=6
```

- `ADO_ORG` — the segment after `dev.azure.com/` in your board URL.
- `ADO_PROJECT` — your team project name.
- `DAILY_BUDGET` — total whole hours to log per day.

> `.env` is git-ignored. Your token never leaves your machine.

---

## 5. Test it (safe — no changes)

```bash
python3 smart_ado_hours.py --dry-run
```

You should see something like:

```
================================================================
Smart ADO Hours - 2026-08-13  (budget 6h)
================================================================
  AB#428823 [NFT] +6h  (C:42->48, R:18->12)
      Upgrade WMS Android Applications for Android 14 & 15 Compati
================================================================
Total to log: 6h

[DRY RUN] No changes made.
```

If you see `ERROR: ADO_PAT not set` → recheck `.env`.
If you see an auth error → confirm the PAT scope is **Work Items (Read & Write)** and the org/project are correct.

When the plan looks right, do one real manual run:

```bash
python3 smart_ado_hours.py --force
```

Check your ADO board — the hours should be updated, and you should get a desktop notification.

---

## 6. Schedule with cron

```bash
chmod +x run_cron.sh install_cron.sh
./install_cron.sh
```

This installs:

```
*/15 16 * * 1-5 "/full/path/to/run_cron.sh"
```

Verify:

```bash
crontab -l
```

The job fires every 15 min between 4:00–4:59 PM, Mon–Fri. The script self-locks so it does the actual update **only once per day** — the frequent trigger just ensures it runs the first time your machine is on during that window.

> **Using a virtualenv?** Edit `run_cron.sh` and replace
> `/usr/bin/env python3` with the full path to your venv python, e.g.
> `"$SCRIPT_DIR/.venv/bin/python3"`.

### Change the time window

Edit the cron entry (`crontab -e`). The `16` is the hour (24h clock). Examples:
- Noon window: `*/15 12 * * 1-5`
- 5–6 PM window: `*/15 17 * * 1-5`

---

## 7. Verify it's working

After the window passes (or after a `--force` run), check:

```bash
# What the last run did
cat data/hours_update_log.json

# Cron output over time
cat logs/hours_cron.log
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ADO_PAT not set` | Ensure `.env` exists and has `ADO_PAT=...` (no quotes needed). |
| `401 Unauthorized` | PAT expired or wrong scope. Recreate with Work Items Read & Write. |
| `WIQL query` error | Check `ADO_ORG` / `ADO_PROJECT` match your board URL. |
| No tasks found | You may have no In-Progress NFT/FT/Bug with remaining > 0 in the current sprint. Confirm on your board. |
| No desktop popup | Install `libnotify-bin`. The update still works without it (check the log). |
| Cron never runs | Machine must be on during 4–5 PM. Plain cron does not catch up missed windows. |
| Ran but want to re-run same day | Use `--force` to bypass the daily lock. |

---

## Uninstall

Remove the cron entry:

```bash
crontab -e   # delete the two lines for the auto-logger
```

Then delete the folder. No system-wide changes are made.
