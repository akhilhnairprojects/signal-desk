"""Push notifications: weekly digest and tier-change alerts.

Two channels, both optional and configured purely through environment
variables (GitHub Actions secrets) - the script prints and exits cleanly
when neither is configured, so workflows never fail on missing setup:

  Email:  SMTP_USER + SMTP_PASSWORD + DIGEST_TO
          (a Gmail address + app password works: Google Account ->
           Security -> 2-Step Verification -> App passwords)
  Teams:  TEAMS_WEBHOOK_URL (channel -> Connectors -> Incoming Webhook)

Usage:
  python scripts/send_digest.py --weekly   # Friday digest summary
  python scripts/send_digest.py --alerts   # only if tiers changed tonight
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from src import config


def weekly_body() -> str | None:
    path = config.RESULTS_DIR / "weekly_digest.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    lines = [
        f"Weekly account intelligence digest ({d['generated_at'][:10]})",
        "",
        f"- Accounts tracked: {d['accounts']}",
        f"- Notes added this week: {d['notes_last_7d']}",
        f"- KB edits this week: {d['kb_edits_last_7d']}",
        f"- User-added companies: {d['custom_accounts']}",
        f"- Accounts with fresh news: {d['news_coverage']}",
    ]
    movers = [m for m in d.get("top_movers", [])
              if isinstance(m.get("account"), str)]
    if movers:
        lines += ["", "Biggest score movements vs base:"]
        lines += [f"  - {m['account']}: {m['delta']:+.1f}" for m in movers]
    tiers = d.get("tier_counts", {})
    if tiers:
        lines += ["", "Tiers: " + ", ".join(f"{k} = {v}"
                                            for k, v in sorted(tiers.items()))]
    lines += ["", "Open the dashboard for details."]
    return "\n".join(lines)


def alerts_body() -> str | None:
    path = config.RESULTS_DIR / "tier_changes.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    changes = d.get("changes", [])
    if not changes:
        return None
    lines = [f"Tier alert - {len(changes)} account(s) changed tier in "
             f"tonight's refresh ({d['generated_at'][:10]}):", ""]
    lines += [f"  - {c['account']}: {c['from']} -> {c['to']} "
              f"(score {c['score']})" for c in changes]
    lines += ["", "Open the dashboard for the why (news, notes, KB)."]
    return "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    to = os.environ.get("DIGEST_TO", "").strip()
    if not (user and password and to):
        return False
    msg = MIMEText(body)
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.login(user, password)
        server.sendmail(user, [a.strip() for a in to.split(",")],
                        msg.as_string())
    return True


def send_teams(body: str) -> bool:
    url = os.environ.get("TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        return False
    requests.post(url, json={"text": body.replace("\n", "\n\n")},
                  timeout=15).raise_for_status()
    return True


def main() -> None:
    mode = "--alerts" if "--alerts" in sys.argv else "--weekly"
    body = alerts_body() if mode == "--alerts" else weekly_body()
    if body is None:
        print(f"{mode}: nothing to send (no changes / no digest yet).")
        return
    subject = ("Account intelligence: tier changes" if mode == "--alerts"
               else "Account intelligence: weekly digest")
    sent = []
    try:
        if send_email(subject, body):
            sent.append("email")
    except Exception as e:
        print(f"Email failed: {type(e).__name__}: {e}")
    try:
        if send_teams(body):
            sent.append("Teams")
    except Exception as e:
        print(f"Teams failed: {type(e).__name__}: {e}")
    print(f"Sent via {', '.join(sent)}." if sent else
          "No channel configured (set SMTP_USER/SMTP_PASSWORD/DIGEST_TO "
          "and/or TEAMS_WEBHOOK_URL as repository secrets) - skipped.")


if __name__ == "__main__":
    main()
