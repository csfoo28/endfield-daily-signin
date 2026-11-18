#!/usr/bin/env python3
"""Arknights: Endfield daily check-in on SKPort (stdlib only).

Env:
  ACCOUNT_TOKEN    one token, or several separated by commas
  DISCORD_WEBHOOK  optional Discord webhook URL
  RUN_TIMES        daily UTC run times for --loop (default "20:30,08:30")
Flags:
  --loop           run now, then on schedule forever
  --test-discord   send a sample embed to the webhook and exit
Exit code 0 = all accounts claimed or already claimed; 1 = something failed.
"""
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

APP_CODE = "6eb76d4e13aa36e6"
PLATFORM = "3"
VNAME = "1.0.0"
ZONAI = "https://zonai.skport.com"
UTC8 = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://game.skport.com",
    "Referer": "https://game.skport.com/",
}
SIGN_IN_PAGE = "https://game.skport.com/endfield/sign-in"
COLOR = {"claimed": 0x57F287, "already": 0x99AAB5, "failed": 0xED4245}


def http(method, url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**BASE_HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def sign(path, ts, key):
    hdr = json.dumps({"platform": PLATFORM, "timestamp": ts, "dId": "", "vName": VNAME},
                     separators=(",", ":"))
    h = hmac.new(key.encode(), f"{path}{ts}{hdr}".encode(), hashlib.sha256).hexdigest()
    return hashlib.md5(h.encode()).hexdigest()


def zonai_headers(cred, path, sign_key=None, role=None):
    ts = str(int(time.time()))
    h = {"cred": cred, "platform": PLATFORM, "vname": VNAME,
         "timestamp": ts, "sk-language": "en"}
    if sign_key:
        h["sign"] = sign(path, ts, sign_key)
    if role:
        h["sk-game-role"] = role
    return h


def check_in(account_token):
    """Returns dict: status ('claimed'|'already'|'failed'), nick, server, rewards, error."""
    res = {"status": "failed", "nick": None, "server": None, "rewards": [], "error": None}

    def fail(msg):
        res["error"] = msg
        return res

    # 1. account token -> OAuth code
    _, d = http("POST", "https://as.gryphline.com/user/oauth2/v2/grant",
                body={"token": account_token, "appCode": APP_CODE, "type": 0})
    code = (d.get("data") or {}).get("code")
    if d.get("status") != 0 or not code:
        return fail(f"Login failed, the token may have expired: {d.get('msg') or d.get('message') or d}")

    # 2. OAuth code -> cred
    _, d = http("POST", f"{ZONAI}/web/v1/user/auth/generate_cred_by_code",
                headers={"platform": PLATFORM}, body={"kind": 1, "code": code})
    cred = (d.get("data") or {}).get("cred")
    if not cred:
        return fail(f"generate_cred failed: {d}")

    # 3. cred -> signing key
    _, d = http("GET", f"{ZONAI}/web/v1/auth/refresh",
                headers=zonai_headers(cred, "/web/v1/auth/refresh"))
    key = (d.get("data") or {}).get("token")
    if not key:
        return fail(f"auth refresh failed: {d}")

    # 4. find the Endfield role (sk-game-role = 3_<roleId>_<serverId>)
    path = "/api/v1/game/player/binding"
    _, d = http("GET", ZONAI + path, headers=zonai_headers(cred, path, key))
    role = None
    for app in (d.get("data") or {}).get("list") or []:
        if app.get("appCode") == "endfield" and app.get("bindingList"):
            b = app["bindingList"][0]
            r = b.get("defaultRole") or (b.get("roles") or [None])[0]
            if r:
                role = f"3_{r.get('roleId')}_{r.get('serverId')}"
                res["nick"] = r.get("nickname") or str(r.get("roleId"))
                res["server"] = r.get("serverName")
    if not role:
        return fail(f"No Endfield character is linked to this account: {d}")

    # 5. claim
    path = "/web/v1/game/endfield/attendance"
    status, d = http("POST", ZONAI + path, headers=zonai_headers(cred, path, key, role))
    c, msg = d.get("code", -1), str(d.get("message", ""))
    if c == 0:
        data = d.get("data") or {}
        info = data.get("resourceInfoMap") or {}
        for a in data.get("awardIds") or []:
            item = info.get(a.get("id"))
            if item:
                res["rewards"].append({"name": str(item.get("name", "?")),
                                       "count": item.get("count", 1),
                                       "icon": item.get("icon")})
        res["status"] = "claimed"
        return res
    if c in (1001, 10001) or "already" in msg.lower() or "again" in msg.lower() or status == 403:
        res["status"] = "already"
        return res
    return fail(f"Check-in failed: code={c} {msg}")


def reward_name(name):
    # The API gives names like "Talosian Credit Notes|T-Creds": show the short name.
    parts = [p.strip() for p in name.split("|") if p.strip()]
    return parts[-1] if parts else name


def fmt_count(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def text_line(i, r):
    who = f"[{r['nick']}]" if r["nick"] else ""
    if r["status"] == "claimed":
        items = ", ".join(f"{reward_name(x['name'])} x{fmt_count(x['count'])}" for x in r["rewards"])
        return f"account {i}: OK {who} claimed: {items or 'ok'}"
    if r["status"] == "already":
        return f"account {i}: OK {who} already claimed today"
    return f"account {i}: FAIL {who} {r['error']}"


def build_embed(r, now):
    title = {"claimed": "✅ Daily check-in claimed",
             "already": "☑️ Already checked in today",
             "failed": "❌ Daily check-in failed"}[r["status"]]
    fields = []
    if r["nick"]:
        who = r["nick"] + (f" · {r['server']}" if r["server"] else "")
        fields.append({"name": "Operator", "value": who, "inline": True})
    fields.append({"name": "Date (UTC+8)", "value": now.astimezone(UTC8).strftime("%a, %d %b %Y"),
                   "inline": True})
    embed = {"title": title, "url": SIGN_IN_PAGE, "color": COLOR[r["status"]],
             "fields": fields, "timestamp": now.isoformat(),
             "footer": {"text": "Arknights: Endfield · SKPort auto check-in"}}
    if r["rewards"]:
        lines = [f"**{reward_name(x['name'])}** × {fmt_count(x['count'])}" for x in r["rewards"]]
        fields.insert(0, {"name": "Reward", "value": "\n".join(lines), "inline": False})
        icon = r["rewards"][0].get("icon")
        if isinstance(icon, str) and icon.startswith("http"):
            embed["thumbnail"] = {"url": icon}
    if r["status"] == "failed":
        embed["description"] = (f"```{str(r['error'])[:900]}```\n"
                                "If the token expired, copy a new one and recreate the container.")
    return embed


def notify(results, now):
    hook = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if not hook:
        return
    embeds = [build_embed(r, now) for r in results][:10]
    st, d = http("POST", hook, body={"username": "Endfield Check-in", "embeds": embeds})
    if st >= 300:
        print(f"Discord webhook error {st}: {d}", flush=True)


def run_once():
    tokens = [t.strip() for t in os.environ.get("ACCOUNT_TOKEN", "").split(",") if t.strip()]
    if not tokens:
        print("ACCOUNT_TOKEN is not set", file=sys.stderr, flush=True)
        return 1
    results = []
    for t in tokens:
        try:
            results.append(check_in(t))
        except Exception as e:  # network errors etc.
            results.append({"status": "failed", "nick": None, "server": None,
                            "rewards": [], "error": f"error: {e}"})
    now = datetime.now(timezone.utc)
    print(f"Endfield check-in {now:%Y-%m-%d %H:%M} UTC\n"
          + "\n".join(text_line(i, r) for i, r in enumerate(results, 1)), flush=True)
    # Ping Discord on failure always, on success only if a reward was newly claimed.
    if any(r["status"] in ("claimed", "failed") for r in results):
        notify(results, now)
    return 0 if all(r["status"] != "failed" for r in results) else 1


def test_discord():
    now = datetime.now(timezone.utc)
    sample = [
        {"status": "claimed", "nick": "Test Operator", "server": "Asia", "error": None,
         "rewards": [{"name": "Talosian Credit Notes|T-Creds", "count": 2000, "icon": None}]},
        {"status": "failed", "nick": None, "server": None, "rewards": [],
         "error": "Login failed, the token may have expired: Login status expired."},
    ]
    notify(sample, now)
    print("sent test embeds", flush=True)


def loop():
    """Run now, then every day at the UTC times in RUN_TIMES (default 20:30,08:30)."""
    times = sorted(tuple(map(int, t.split(":")))
                   for t in os.environ.get("RUN_TIMES", "20:30,08:30").split(","))
    run_once()
    while True:
        now = datetime.now(timezone.utc)
        cands = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in times]
        future = [c for c in cands if c > now] or [c + timedelta(days=1) for c in cands]
        nxt = min(future) + timedelta(seconds=random.randint(0, 900))
        print(f"next run at {nxt:%Y-%m-%d %H:%M:%S} UTC", flush=True)
        time.sleep(max(1, (nxt - datetime.now(timezone.utc)).total_seconds()))
        run_once()


if __name__ == "__main__":
    if "--test-discord" in sys.argv:
        test_discord()
        sys.exit(0)
    if "--loop" in sys.argv:
        loop()
    sys.exit(run_once())
