# Deploying NyaySutra AI on Oracle Cloud (Always Free)

Step-by-step for a student budget: **₹0 for the server**. The database and files stay in Supabase (Mumbai); only the
app moves to Oracle. Time needed: about 1–2 hours the first time (most of it waiting for Oracle and DNS).

What you end up with: `https://<your-name>.duckdns.org` serving NyaySutra over HTTPS, with Caddy in front, the app in
a Docker container, automatic security updates and an uptime alert.

**You do the account, card and password steps yourself.** Claude cannot create accounts or enter card details,
passwords or keys. Everything else is a script or a copy-paste command.

---

## Measured needs (November 2026)

| | NyaySutra uses | Oracle Always Free gives (reported 2026 limit) |
|---|---|---|
| Memory | ~0.5 GB app, ~1.5 GB with OS + Caddy + OCR spikes | 12 GB (Ampere A1, 2 OCPU) |
| Disk | ~3 GB (image + law library) | up to 200 GB boot volumes |
| CPU | 2 cores are plenty for a pilot | 2 OCPU (ARM) |

The Docker image is built and health-checked on ARM in CI on every push (`container-arm64` job), so it runs on
Ampere A1.

---

## 1. Create the Oracle Cloud account (you)

1. Sign up at **cloud.oracle.com** → *Start for free*. A debit/credit card is needed to verify identity; the
   Always Free resources are not charged.
2. **Home region: choose _India West (Mumbai)_ or _India South (Hyderabad)_.** It cannot be changed later, and it should
   be close to Supabase (Mumbai).
3. Recommended once the account works: **upgrade to Pay As You Go** (*Billing → Upgrade and manage payment*). Always
   Free resources stay free, but idle Always Free servers on free-trial accounts can be reclaimed by Oracle, and paid
   accounts get A1 capacity more easily. Immediately add a **budget alert** (*Billing → Budgets*, e.g. ₹100) so any
   accidental paid resource e-mails you.

## 2. Create the network (you, 5 minutes)

1. *Networking → Virtual cloud networks → Start VCN Wizard → **Create VCN with Internet Connectivity*** → defaults →
   Create.
2. Open the new VCN → *Public Subnet* → its *Default Security List* → **Add Ingress Rules**:

   | Source CIDR | Protocol | Destination port | Why |
   |---|---|---|---|
   | `0.0.0.0/0` | TCP | 80 | HTTP (Caddy redirects to HTTPS, and Let's Encrypt validation) |
   | `0.0.0.0/0` | TCP | 443 | HTTPS |
   | `0.0.0.0/0` | UDP | 443 | HTTP/3 (optional) |

   Port 22 (SSH) is already open. Do **not** open 8000 — the app must only be reachable through Caddy.

## 3. Create an SSH key on your laptop (you, 1 minute)

In PowerShell or the VS Code terminal:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\nyaysutra_oracle"
```

Press Enter for no passphrase, or set one. This creates `nyaysutra_oracle` (private: never share it) and
`nyaysutra_oracle.pub` (public: you paste this into Oracle).

## 4. Create the server (you, 5 minutes — sometimes a few retries)

*Compute → Instances → Create instance*:

| Setting | Value |
|---|---|
| Name | `nyaysutra` |
| Image | **Canonical Ubuntu 24.04** (the aarch64 build is selected automatically for Ampere) |
| Shape | *Change shape* → **Ampere** → **VM.Standard.A1.Flex**, **2 OCPU, 12 GB memory** (or whatever the Always Free limit shows) |
| Networking | the VCN from step 2, **public subnet**, *Assign a public IPv4 address* = yes |
| SSH keys | *Paste public keys* → contents of `nyaysutra_oracle.pub` |
| Boot volume | 50 GB is plenty |

**"Out of capacity"?** This is common for free ARM servers. Try another *Availability domain* in the same screen,
try again at a different time of day, or (with a Pay As You Go account) it usually succeeds sooner. It is not your
mistake.

Note the **public IP address** shown on the instance page.

## 5. Prepare the server (script)

From your laptop:

```powershell
ssh -i "$env:USERPROFILE\.ssh\nyaysutra_oracle" ubuntu@PUBLIC_IP
```

On the server:

```bash
curl -fsSLO https://raw.githubusercontent.com/SwarangiK-21/NyaySutra-AI/main/deploy/oracle/setup-server.sh
bash setup-server.sh
exit
```

(Until the redesign is merged into `main`, use `feature/ui-redesign` instead of `main` in that URL.)

The script installs updates and automatic security updates, opens ports 80/443 in Ubuntu's own firewall (Oracle's
images block them by default — the most common reason a site "doesn't load"), installs Docker with log rotation, and
clones the repository to `~/nyaysutra`. Log in again afterwards so Docker works without `sudo`.

## 6. A free web address (you, 5 minutes)

HTTPS needs a name, not a bare IP.

1. Go to **duckdns.org**, sign in, create a subdomain, e.g. `nyaysutra-yourname` → `nyaysutra-yourname.duckdns.org`.
2. Put the server's **public IP** in its *current ip* field → *update ip*.

(Your own domain works the same way: create an **A record** pointing at the public IP.)

## 7. Copy the secrets and the law library (from your laptop)

The `.env` file and the 103 India Code acts imported at run time are **not in Git** (on purpose). Copy them:

```powershell
cd "D:\PROJECT\nyaysutra-ai\nyaysutra-ai\nyaysutra"
tar -czf states.tgz data/library/bare_acts/states data/library/judgments/supreme_court
scp -i "$env:USERPROFILE\.ssh\nyaysutra_oracle" .env states.tgz ubuntu@PUBLIC_IP:~/nyaysutra/
```

On the server:

```bash
cd ~/nyaysutra
git checkout feature/ui-redesign   # until it is merged; then stay on main
tar -xzf states.tgz && rm states.tgz
chmod 600 .env
```

## 8. Production settings (on the server)

Edit `~/nyaysutra/.env` (`nano .env`) and make sure these lines are present (replace the address):

```ini
PUBLIC_URL=https://nyaysutra-yourname.duckdns.org
ALLOWED_HOSTS=nyaysutra-yourname.duckdns.org
SIGNUP_MODE=invite_only
AUTH_MODE=supabase
```

Keep all existing Supabase and AI keys. Never commit `.env`. Then:

```bash
echo "SITE_ADDRESS=nyaysutra-yourname.duckdns.org" > ~/nyaysutra/deploy/.env
```

In the **Supabase dashboard → Authentication → URL Configuration**: *Site URL* =
`https://nyaysutra-yourname.duckdns.org`, and add `https://nyaysutra-yourname.duckdns.org/**` to *Redirect URLs*
(otherwise sign-up and password-reset e-mails point to 127.0.0.1).

## 9. Start

```bash
cd ~/nyaysutra/deploy
docker compose up -d --build        # first build ~5–10 minutes on ARM
docker compose logs -f app          # Ctrl+C to stop watching; wait for "Embedding + reranker models ready"
```

Check in your browser:

* `https://nyaysutra-yourname.duckdns.org/api/health` → `{"ok": true, "database": true, "index_loaded": true}`
* `https://nyaysutra-yourname.duckdns.org` → the Ask page with a padlock. Sign in with your account.

If HTTPS fails: DNS not updated yet (wait a few minutes), or ports 80/443 not open (steps 2 and 5).

First administrator, if needed (only once):

```bash
docker compose exec app python scripts/bootstrap_admin.py --email you@example.org
```

## 10. Keep it alive and watched (you, 5 minutes)

* **UptimeRobot** (free): HTTP(s) monitor on `https://nyaysutra-yourname.duckdns.org/api/health`, every 5 minutes,
  e-mail alerts. These checks also count as database activity, which keeps the free Supabase project from pausing
  after 7 quiet days.
* **Oracle idle reclamation:** Always Free servers whose CPU, network and memory stay very low for 7 days may be
  stopped. A Pay As You Go account (step 1.3) is the reliable protection; check Oracle's current Always Free page.

## 11. Updating to a new version

```bash
cd ~/nyaysutra && git pull
cd deploy && docker compose up -d --build
```

Database migrations (`supabase/migrations/*`) are applied to Supabase separately, before deploying code that needs
them; the app refuses to start against an older schema.

## Security checklist after the first start

- [ ] `https://` works and `http://` redirects to it
- [ ] `http://PUBLIC_IP:8000` does **not** load (the app is only reachable through Caddy)
- [ ] `SIGNUP_MODE=invite_only` (a stranger signing up gets no access)
- [ ] MFA turned on for your Oracle, Supabase and GitHub accounts
- [ ] Budget alert set in Oracle billing
- [ ] `.env` is `chmod 600` and not in Git
