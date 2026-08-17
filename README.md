# Smart ADO Hours Auto-Logger

Automatically logs your daily work hours to Azure DevOps so you never forget to update your sprint tasks.

Every weekday it discovers all your **In-Progress** work items in the **current sprint**, distributes a fixed daily budget of whole hours equally across them, updates **Completed Work** / **Remaining Work**, and pops a desktop notification with a summary.

---

## What it does

- 🔍 **Auto-discovers** your tasks — no hardcoded IDs. Uses a WIQL query scoped to `@Me` + `@CurrentIteration`, so it keeps working sprint after sprint.
- ➗ **Distributes hours** — splits your daily budget (default **6h**) equally across all active tasks, in **whole numbers only**.
- 🧢 **Caps at remaining** — never pushes a task's Remaining Work below 0. If less than the budget is left in total, it logs only what remains.
- 🔒 **Runs once per day** — a local lock file prevents double-logging even if triggered multiple times.
- 📅 **Skips weekends** — no logging on Saturday/Sunday.
- 🔔 **Desktop notification** — shows a summary of what was logged.

### Which tasks qualify?

A work item is updated only if **all** of these are true:

| Condition | Value |
|-----------|-------|
| Assigned To | You (the PAT owner, via `@Me`) |
| Iteration | Current sprint (`@CurrentIteration`) |
| State | `In Progress` |
| Work Item Type | `NFT`, `FT`, or `Bug` |
| Remaining Work | `> 0` |

---

## How the distribution works

The daily budget is split equally, one whole hour at a time (round-robin), skipping any task that hits its remaining cap.

**Example — 6h budget:**

| Active tasks (remaining) | Allocation | Total |
|--------------------------|-----------|-------|
| `[18, 8, 4]` | `[2, 2, 2]` | 6h |
| `[18, 8, 4, 10]` | `[2, 2, 1, 1]` | 6h |
| `[1, 10]` | `[1, 5]` | 6h |
| `[1, 1, 1, 1, 1, 1, 1]` (7 tasks) | `[1,1,1,1,1,1,0]` | 6h |
| `[2, 1]` (only 3h left total) | `[2, 1]` | 3h |
| `[18]` (single task) | `[6]` | 6h |

For each task: `Completed += allocation`, `Remaining = max(0, Remaining - allocation)`.

---

## Quick start

```bash
git clone https://github.com/MandalKushagra/ado-hours-autologger.git
cd ado-hours-autologger

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
#   edit .env → paste your ADO_PAT, set ADO_ORG / ADO_PROJECT

# 3. Test without changing anything
python3 smart_ado_hours.py --dry-run

# 4. Schedule it (runs 4-5 PM, Mon-Fri)
chmod +x run_cron.sh install_cron.sh
./install_cron.sh
```

See [SETUP.md](SETUP.md) for the full step-by-step guide (PAT creation, cron internals, troubleshooting).

---

## Usage

```bash
python3 smart_ado_hours.py            # normal run (respects daily lock + weekends)
python3 smart_ado_hours.py --dry-run  # preview the plan, change nothing
python3 smart_ado_hours.py --force    # ignore daily lock + weekend guard (manual run)
```

---

## Configuration

All config lives in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ADO_PAT` | — | **Required.** Personal Access Token with Work Items (Read & Write). |
| `ADO_ORG` | `delhivery` | Azure DevOps organization. |
| `ADO_PROJECT` | `GM-WMS` | Azure DevOps project. |
| `DAILY_BUDGET` | `6` | Total whole hours to distribute per day. |

---

## Files

| File | Purpose |
|------|---------|
| `smart_ado_hours.py` | Main script — discovery, distribution, update, notify. |
| `run_cron.sh` | Cron wrapper (sets `DISPLAY`/`DBUS` so notifications work). |
| `install_cron.sh` | One-shot cron installer. |
| `.env.example` | Config template — copy to `.env`. |
| `requirements.txt` | Python dependencies. |
| `data/hours_update_log.json` | Runtime — last run date + 90-day history (git-ignored). |
| `logs/hours_cron.log` | Runtime — cron output (git-ignored). |

---

## Schedule details

The cron entry fires every 15 minutes between 4:00–4:59 PM, Monday–Friday:

```
*/15 16 * * 1-5 "/path/to/run_cron.sh"
```

The script itself enforces the "once per day" rule and skips weekends, so the frequent trigger simply means: *"run the first time the machine is on during the 4–5 PM window."* If your machine is off for the whole window, it won't run that day (plain cron does not catch up missed runs).

---

## Security

- Your PAT lives only in `.env`, which is **git-ignored**. It is never committed.
- The tool only touches the two effort fields (Completed / Remaining Work) on work items assigned to you.

---

## Requirements

- Python 3.8+
- Linux with `notify-send` (from `libnotify-bin`) for desktop notifications — optional; the tool still runs and logs without it.
- An Azure DevOps PAT with Work Items (Read & Write) scope.
