#!/usr/bin/env python3
"""
Smart ADO Hours Auto-Updater.

Discovers all your In-Progress tasks (NFT/FT/Bug) in the current sprint,
distributes a fixed daily budget of whole hours equally across them,
caps each task at its remaining work, and updates Completed/Remaining Work.

Behaviour:
  - Daily budget: DAILY_BUDGET_HOURS total, split EQUALLY, WHOLE numbers only
  - Qualifying: assigned to @Me, @CurrentIteration, State='In Progress',
                WorkItemType in (NFT, FT, Bug), RemainingWork > 0
  - Never pushes RemainingWork below 0 (each task capped at its remaining)
  - If total remaining < budget -> logs only what's left
  - Idempotent: runs once per day (data/hours_update_log.json)
  - Skips weekends (Sat/Sun)
  - Desktop notification with summary after run (Linux notify-send)

Usage:
  python3 smart_ado_hours.py            # normal run (respects daily lock + weekends)
  python3 smart_ado_hours.py --dry-run  # show plan, change nothing
  python3 smart_ado_hours.py --force    # ignore daily lock + weekend guard

Environment (.env or shell):
  ADO_PAT        Personal Access Token (Work Items Read & Write)  [required]
  ADO_ORG        default: delhivery
  ADO_PROJECT    default: GM-WMS
  DAILY_BUDGET   default: 6
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, date

try:
    import requests
except ImportError:
    print("ERROR: 'requests' required -> pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QUALIFYING_TYPES = ("NFT", "FT", "Bug")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_DIR, "data", "hours_update_log.json")

ORG = os.environ.get("ADO_ORG", "delhivery")
PROJECT = os.environ.get("ADO_PROJECT", "GM-WMS")
DAILY_BUDGET_HOURS = int(os.environ.get("DAILY_BUDGET", "6"))
API_VERSION = "7.1"


# ---------------------------------------------------------------------------
# Auth / HTTP
# ---------------------------------------------------------------------------
def get_pat():
    pat = os.environ.get("ADO_PAT")
    if not pat:
        env_path = os.path.join(PROJECT_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("ADO_PAT="):
                        pat = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not pat or pat == "your_ado_personal_access_token":
        print("ERROR: ADO_PAT not set. Add it to .env")
        print("Create at: https://dev.azure.com/<org>/_usersSettings/tokens")
        print("Scope: Work Items (Read & Write)")
        sys.exit(1)
    return pat


def _auth(pat, patch=False):
    encoded = base64.b64encode(f":{pat}".encode()).decode()
    ctype = "application/json-patch+json" if patch else "application/json"
    return {"Authorization": f"Basic {encoded}", "Content-Type": ctype}


def query_current_sprint_tasks(pat):
    """WIQL: my In-Progress NFT/FT/Bug in current iteration with remaining > 0."""
    wiql = {
        "query": (
            "SELECT [System.Id] FROM WorkItems WHERE "
            "[System.AssignedTo] = @Me "
            "AND [System.IterationPath] = @CurrentIteration "
            "AND [System.State] = 'In Progress' "
            "AND [System.WorkItemType] IN ('NFT', 'FT', 'Bug') "
            "AND [Microsoft.VSTS.Scheduling.RemainingWork] > 0"
        )
    }
    url = f"https://dev.azure.com/{ORG}/{PROJECT}/_apis/wit/wiql"
    resp = requests.post(url, headers=_auth(pat), params={"api-version": API_VERSION}, json=wiql)
    if resp.status_code != 200:
        print(f"ERROR WIQL query: {resp.status_code} - {resp.text}")
        sys.exit(1)
    return [w["id"] for w in resp.json().get("workItems", [])]


def get_work_items(pat, ids):
    if not ids:
        return []
    url = f"https://dev.azure.com/{ORG}/{PROJECT}/_apis/wit/workitems"
    params = {
        "ids": ",".join(str(i) for i in ids),
        "api-version": API_VERSION,
        "fields": ",".join([
            "System.Id", "System.Title", "System.WorkItemType",
            "Microsoft.VSTS.Scheduling.CompletedWork",
            "Microsoft.VSTS.Scheduling.RemainingWork",
        ]),
    }
    resp = requests.get(url, headers=_auth(pat), params=params)
    if resp.status_code != 200:
        print(f"ERROR fetching items: {resp.status_code} - {resp.text}")
        sys.exit(1)
    return resp.json().get("value", [])


def update_work_item(pat, wid, completed, remaining):
    url = f"https://dev.azure.com/{ORG}/{PROJECT}/_apis/wit/workitems/{wid}"
    ops = [
        {"op": "replace", "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork", "value": completed},
        {"op": "replace", "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork", "value": remaining},
    ]
    resp = requests.patch(url, headers=_auth(pat, patch=True),
                          params={"api-version": API_VERSION}, json=ops)
    if resp.status_code != 200:
        print(f"ERROR updating {wid}: {resp.status_code} - {resp.text}")
        return False
    return True


# ---------------------------------------------------------------------------
# Distribution logic (whole numbers, equal split, capped at remaining)
# ---------------------------------------------------------------------------
def distribute_hours(tasks, budget):
    """
    tasks: list of dicts with an int 'remaining' key.
    Returns whole-number allocations aligned with tasks order.

    Equal split via round-robin: hand out 1h at a time to each task in turn,
    skipping tasks that reached their remaining cap. Total = min(budget, sum remaining).
    """
    n = len(tasks)
    alloc = [0] * n
    if n == 0:
        return alloc

    caps = [int(t["remaining"]) for t in tasks]
    to_give = min(budget, sum(caps))

    given, idx, safety = 0, 0, 0
    max_iters = to_give * (n + 1) + n + 1
    while given < to_give and safety < max_iters:
        if alloc[idx] < caps[idx]:
            alloc[idx] += 1
            given += 1
        idx = (idx + 1) % n
        safety += 1
    return alloc


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def already_ran_today():
    if not os.path.exists(LOG_FILE):
        return False
    try:
        with open(LOG_FILE) as f:
            return json.load(f).get("last_run_date") == date.today().isoformat()
    except Exception:
        return False


def record_run(summary):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    history = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                history = json.load(f).get("history", [])
        except Exception:
            history = []
    history.append({"timestamp": datetime.now().isoformat(), "summary": summary})
    with open(LOG_FILE, "w") as f:
        json.dump({"last_run_date": date.today().isoformat(),
                   "history": history[-90:]}, f, indent=2)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------
def notify(title, message):
    try:
        subprocess.run(["notify-send", title, message], check=False)
    except FileNotFoundError:
        pass
    print(f"\n[{title}] {message}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Smart ADO daily hours updater")
    ap.add_argument("--dry-run", action="store_true", help="Show plan without updating")
    ap.add_argument("--force", action="store_true", help="Ignore daily lock and weekend guard")
    args = ap.parse_args()

    today = date.today()

    if today.weekday() >= 5 and not args.force:
        print("Weekend - skipping.")
        return

    if already_ran_today() and not args.force and not args.dry_run:
        print(f"Already ran today ({today.isoformat()}). Skipping.")
        return

    pat = get_pat()

    ids = query_current_sprint_tasks(pat)
    if not ids:
        notify("ADO Hours", "No active tasks with remaining work in current sprint.")
        if not args.dry_run:
            record_run("No active tasks")
        return

    items = get_work_items(pat, ids)
    tasks = []
    for it in items:
        f = it.get("fields", {})
        tasks.append({
            "id": it["id"],
            "title": f.get("System.Title", "?"),
            "type": f.get("System.WorkItemType", "?"),
            "completed": int(f.get("Microsoft.VSTS.Scheduling.CompletedWork", 0) or 0),
            "remaining": int(f.get("Microsoft.VSTS.Scheduling.RemainingWork", 0) or 0),
        })

    tasks.sort(key=lambda t: t["id"])
    alloc = distribute_hours(tasks, DAILY_BUDGET_HOURS)
    total_alloc = sum(alloc)

    print(f"\n{'='*64}")
    print(f"Smart ADO Hours - {today.isoformat()}  (budget {DAILY_BUDGET_HOURS}h)")
    print(f"{'='*64}")
    for t, a in zip(tasks, alloc):
        new_c = t["completed"] + a
        new_r = max(0, t["remaining"] - a)
        flag = "" if a > 0 else "  (skipped)"
        print(f"  AB#{t['id']} [{t['type']}] +{a}h  "
              f"(C:{t['completed']}->{new_c}, R:{t['remaining']}->{new_r}){flag}")
        print(f"      {t['title'][:60]}")
    print(f"{'='*64}")
    print(f"Total to log: {total_alloc}h")

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    if total_alloc == 0:
        notify("ADO Hours", "Nothing to log (no remaining hours).")
        record_run("Nothing to log")
        return

    parts, ok = [], 0
    for t, a in zip(tasks, alloc):
        if a == 0:
            continue
        new_c = t["completed"] + a
        new_r = max(0, t["remaining"] - a)
        if update_work_item(pat, t["id"], new_c, new_r):
            ok += 1
            parts.append(f"AB#{t['id']} +{a}h")

    summary = f"Logged {total_alloc}h across {ok} task(s): " + ", ".join(parts)
    notify("ADO Hours Updated", summary)
    record_run(summary)
    print(f"\nDone at {datetime.now().strftime('%H:%M')}")


if __name__ == "__main__":
    main()
