# Deploy AuEdge to Railway (via GitHub)

AuEdge then runs 24/7 on Railway: analysis every 15 minutes, the demo account, journal and backups, reachable from any
browser or phone with your password. Your PC is no longer needed.

**Cost:** Railway's Hobby plan, about **$5 / month** (the free trial credit runs out quickly for an always-on app).

---

## Before you start: what goes to GitHub, and what doesn't

`.gitignore` keeps these **out of GitHub**:
- `.env`, which holds your secrets
- `data/`, which holds your journal, demo trades, history and backups
- `.venv/` and caches

**Use a PRIVATE GitHub repository anyway.**

---

## 1. Put the code on GitHub (about 10 minutes, once)

1. Install **Git for Windows** if it isn't installed: https://git-scm.com/download/win
2. On github.com, click **New repository**, name it `auedge`, choose **Private**, and click **Create**. Don't add a README.
3. Open a terminal in the AuEdge folder: right-click the folder → *Open in Terminal*. Then run:

```bash
git init
git add .
git commit -m "AuEdge"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/auedge.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub name. If Git asks you to sign in, a browser window opens; sign in to GitHub there.

**Check:** on github.com your repo shows `app.py`, `agents/`, `core/`, `static/`, `deploy/` and `railway.json`, but **no `data/` folder and no `.env` file**.

### Optional: bring your current records along

This copies your journal, the demo account and the candle history to the server on its first start.

```bash
powershell -ExecutionPolicy Bypass -File tools\make-seed.ps1
git add -f deploy/seed
git commit -m "first data for the server"
git push
```

Only do this with a **private** repository: the seed contains your journal.

---

## 2. Create the Railway service (about 10 minutes, once)

1. Go to **railway.com**, sign in with GitHub, and pick the **Hobby** plan.
2. Click **New Project → Deploy from GitHub repo → choose `auedge`**. Railway reads `railway.json` and starts AuEdge with `deploy/start.sh`.
3. **Add a disk** so your records survive restarts and updates:
   - Open your service → **Settings → Volumes → Add Volume**.
   - Set the mount path to **`/app/data`**.
4. **Set the password.** Open your service → **Variables** and add:

   | Variable | Value |
   |---|---|
   | `AUEDGE_PASSWORD` | a strong password you choose. You'll type it on the login page |
   | `AUEDGE_SECRET` | any long random text (optional; it keeps you logged in safely) |

   Type these in Railway only, **never in chat or in GitHub**.
5. **Get a web address:** go to **Settings → Networking → Generate Domain**. You get something like `auedge-production.up.railway.app`.
6. Open that address. You should see the **AuEdge sign-in page**. Enter your password, and the app opens.

Railway rebuilds and restarts automatically after every change you push to GitHub (step 3). Your `data/` volume is kept.

---

## 3. Updating later

When AuEdge's code changes on your PC, push it from the AuEdge folder:

```bash
git add .
git commit -m "update"
git push
```

Railway redeploys by itself in 1-3 minutes.

---

## 4. Stop the PC copy

Only **one** copy should trade the demo account. Otherwise you get two different demo results. Once Railway works:
- double-click **Stop AuEdge** on your PC, and
- remove the PC auto-start: `powershell -ExecutionPolicy Bypass -File tools\remove-autostart.ps1`

---

## Good to know

- **Logs:** in Railway, open your service → **Deployments → View logs**. The line `WARNING: AUEDGE_PASSWORD is not set` means step 2.4 is missing.
- **Backups** are written inside the volume (`data/backups`, last 30 days), and the CSV exports go to `data/exports`.
- **Health check:** Railway checks `/icon.svg`. If a deploy shows "unhealthy", look at the logs.
- **Time zone:** all trading-day logic uses New York time internally, so the server's location doesn't matter.
- **Sign-ups:** if Railway says "Sign ups are currently disabled", try again later. That's on their side.
