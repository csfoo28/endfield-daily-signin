# Endfield Daily Sign-in

Automatically claims the **Arknights: Endfield** daily sign-in reward on
[SKPort](https://game.skport.com/endfield/sign-in), every day, from a small Docker container.
It can post the result to a Discord channel.

- One Python file, standard library only (no `pip install`)
- Runs twice a day; "already claimed" is treated as success, so the extra run is harmless
- Supports multiple accounts
- Discord embed notifications when a reward is claimed or something fails

> ⚠️ This uses SKPort's unofficial web API. It can change without notice, and automating it
> may go against SKPort's terms of service. Use at your own risk.

---

## Prerequisites

| You need | Notes |
|---|---|
| An SKPort account with an Endfield character linked | Log in once at <https://game.skport.com/endfield/sign-in> and make sure your character shows up. |
| A machine that is always on | A VPS, home server, NAS, etc. Any OS that runs Docker. |
| Docker with Docker Compose | `docker --version` and `docker compose version` should both work. |
| Your `ACCOUNT_TOKEN` | See [Get your ACCOUNT_TOKEN](#1-get-your-account_token). |
| *(Optional)* A Discord webhook URL | Discord → Channel settings → Integrations → Webhooks → New Webhook → Copy URL. |

No Docker? You only need **Python 3.9+**; see [Run without Docker](#run-without-docker).

---

## Setup

### 1. Get your `ACCOUNT_TOKEN`

The script needs your **long-lived** account token. It is *not* the `SK_OAUTH_CRED_KEY`
cookie you see on the sign-in page; that one expires within minutes and will fail with
`Login status expired`.

1. In your browser, log in at <https://game.skport.com/endfield/sign-in>.
2. In the same browser, open:
   <https://web-api.skport.com/cookie_store/account_token>
3. You'll see something like:
   ```json
   {"code":0,"data":{"content":"xxxxxxxxxxxxxxxx"}}
   ```
   Copy the value of `content`. That is your `ACCOUNT_TOKEN`.

> 🔒 Treat this token like a password. Anyone who has it can act as your SKPort account.
> It stays valid until you log out of SKPort or change your password.

### 2. Get the code onto your server

```bash
git clone https://github.com/csfoo28/endfield-daily-signin.git
cd endfield-daily-signin
```

### 3. Create your `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill it in:

```ini
ACCOUNT_TOKEN=your_token_here
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...   # optional
```

For several accounts, separate tokens with commas: `ACCOUNT_TOKEN=token1,token2`.

`.env` is in `.gitignore`, so your token never gets committed.

### 4. Start it

```bash
docker compose up -d --build
docker compose logs -f
```

You should see something like:

```
Endfield check-in 2026-11-18 16:06 UTC
account 1: OK [YourName] claimed: T-Creds x2,000
next run at 2026-11-18 20:39:43 UTC
```

It checks in once right away, then on the daily schedule. The container restarts on its own
after a crash or reboot (`restart: unless-stopped`).

---

## How to use

### Day to day

Nothing to do: it runs by itself. With a Discord webhook you get:

- 🟢 **Claimed**: the reward and quantity
- 🔴 **Failed**: the error, e.g. an expired token

"Already claimed" runs stay quiet, so you'll get about one message a day.

### Common commands

Run these in the project folder.

| Task | Command |
|---|---|
| See recent logs | `docker compose logs --tail 20` |
| Follow logs live | `docker compose logs -f` |
| Check in right now | `docker compose restart` |
| Send a test Discord message | `docker compose run --rm endfield-checkin --test-discord` |
| Stop | `docker compose down` |
| Update to the latest code | `git pull && docker compose up -d --build` |

### After editing `.env`

`docker compose restart` does **not** reload `.env`. Recreate the container instead:

```bash
docker compose up -d --force-recreate
```

### When the token expires

You'll get a red "Daily check-in failed" message mentioning `Login status expired`.
Get a new token ([step 1](#1-get-your-account_token)), put it in `.env`, and recreate the container.

### Change the schedule

Edit `RUN_TIMES` in `compose.yml`. Times are **UTC**, comma-separated, and each run gets
up to 15 minutes of random delay.

```yaml
RUN_TIMES: "20:30,08:30"   # = 04:30 and 16:30 UTC+8 (SKPort's sign-in day is UTC+8)
```

Then run `docker compose up -d --force-recreate`.

---

## Run without Docker

```bash
export ACCOUNT_TOKEN=your_token_here
export DISCORD_WEBHOOK=https://discord.com/api/webhooks/...   # optional

python3 endfield_checkin.py                 # check in once, then exit
python3 endfield_checkin.py --loop          # check in now, then on schedule, forever
python3 endfield_checkin.py --test-discord  # send sample Discord embeds
```

Exit code is `0` when every account was claimed or already claimed, `1` if any failed,
so a single run also works from cron or Windows Task Scheduler.

---

## How it works

Each run does what the sign-in page does, without a browser:

1. **`as.gryphline.com`**: exchanges `ACCOUNT_TOKEN` for a one-time OAuth code.
2. **`zonai.skport.com`**: exchanges the code for a short-lived `cred` and a signing key.
3. Looks up your linked Endfield character (`/api/v1/game/player/binding`).
4. Sends the check-in (`POST /web/v1/game/endfield/attendance`) with a request signature
   (HMAC-SHA256 then MD5 over the path, timestamp and headers).

Only `ACCOUNT_TOKEN` is stored; the short-lived credentials are created fresh on every run.

## Troubleshooting

| Message | Fix |
|---|---|
| `ACCOUNT_TOKEN is not set` | Fill in `.env`, then `docker compose up -d --force-recreate` (not `restart`). |
| `Login failed, the token may have expired` | Wrong or expired token. Make sure you copied `content` from the `cookie_store` link, not `SK_OAUTH_CRED_KEY`. |
| `No Endfield character is linked` | Open the sign-in page while logged in and link your game account. |
| No Discord messages | Check `DISCORD_WEBHOOK`, then run the `--test-discord` command. Runs that only find "already claimed" don't post. |

## Credits

The API flow is based on community research, especially
[endfield-daily-helper](https://github.com/Chiraitori/endfield-daily-helper).
