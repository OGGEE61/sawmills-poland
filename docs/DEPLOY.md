# Hosting on the company server

Docker Compose on Linux. Four containers: `web` (nginx, the only one with a published port), `app` (serves the CSV lists from the database), `db` (PostgreSQL 16) and `scraper` (a job, not always running).

```
browser on company wifi --> web:80 --allowlist--> /src/dashboard/*   static page
                                              \-> /data/processed/*.csv --> app --> PostgreSQL
scraper job: data/ files --> refresh.sh --> load_db.py --> PostgreSQL
```

The dashboard code is unchanged. The app answers the same URLs it used to read as files, now built from the database.

## What lives where

- **PostgreSQL** holds the four lists the dashboard reads: `leads`, `verification`, `tartaki_ceidg`, `tartaki_full`. Columns are text, as in the CSV.
- **`data/`** (a folder on the server, `DATA_DIR`) holds the raw KRS/CEIDG files and the intermediate CSVs the pipeline works from. The scraper still reads and writes files there; the database is loaded at the end of each run. Back up `data/`: the database can always be rebuilt from it with `python src/server/load_db.py`, but `data/raw` takes hours to collect again.

## Local copy vs server

| | On your PC (development) | On the server (production) |
|---|---|---|
| Start | `venv/bin/python run_dashboard.py`, open http://localhost:8000/src/dashboard/index.html | `docker compose up -d --build` (once; see First install) |
| Data comes from | the CSV files in `data/processed/` | PostgreSQL |
| Database / Docker needed | no | yes |
| Who can open it | you, on this machine | only the company wifi (`ALLOWED_CIDR`) |
| Runs | while the terminal is open | in the background, restarts after a crash or reboot |
| Refresh | `sh src/enrichment/refresh.sh` | monthly timer, or `docker compose --profile jobs run --rm scraper` |

The two do not share data. A refresh on your PC changes your local files only. To push it to the server, `rsync` the `data/` folder over and run the load command from step 5 of First install.

For the server to come back by itself after a reboot, run `sudo systemctl enable docker` once. The containers use `restart: unless-stopped`, so Docker starts them again.

## First install

1. Install Docker Engine and the Compose plugin. Clone the repo to `/opt/sawmills-poland`.
2. `cp .env.example .env` and fill in `POSTGRES_PASSWORD` (`openssl rand -hex 24`) and `ALLOWED_CIDR` (the wifi subnet, see below). Add the optional API keys (`GUS_API_KEY`, `SERPER_API_KEY`, ...) here too.
3. Copy your working data to the server (git has only part of it): `rsync -a data/ server:/opt/sawmills-poland/data/`
4. `docker compose up -d --build`
5. Load the database: `docker compose run --rm --no-deps -v "$PWD/data:/app/data" app python src/server/load_db.py`
6. Open `http://<server>/` from a device on the wifi.

Update later: `git pull && docker compose up -d --build`.

## Company wifi only

The server cannot tell wifi from cable. It sees the **source IP**, so "company wifi" means the subnet or VLAN the wifi hands out (ask whoever runs the network). Put it in `ALLOWED_CIDR`. nginx answers every other address with 403, and the server itself is allowed.

- Only one subnet fits `ALLOWED_CIDR`. For several, add more `allow` lines in `deploy/nginx.conf.template`.
- The server must see the real client address. That holds when clients reach it directly on the LAN. It breaks behind a NAT or a proxy that rewrites the source, and with rootless Docker; then every client looks like one address. Check from a phone on mobile data (must get 403) and from the wifi (must get the page).
- This only works if the wifi is a separate network from guests. If guests share the subnet, they get in too.
- Keep the server off the internet: no port forward from the router. Docker publishes ports around `ufw`, so the nginx allowlist, not `ufw`, is the control. A firewall rule in the `DOCKER-USER` chain would be a second layer.
- Traffic is plain HTTP. The list holds names, phones and emails. Anyone on the allowed subnet can read it on the wire; add TLS (a certificate from your internal CA) if that matters.
- The dashboard still loads PapaParse from cdnjs and the Poland map from GitHub, so browsers need internet access, or those two files need to be hosted on the server.

## Running the scraper

```
docker compose --profile jobs run --rm scraper        # same as the monthly job
```

It runs `src/enrichment/refresh.sh` (KRS walk for new companies, VAT check, EU projects, optional GUS/Google/search sources, crawl, rebuild leads) and reloads the database at the end. A lock stops a second run while one is going. The server needs outbound internet. Optional keys come from `.env`; searches are capped by `SEARCH_LIMIT` (default 50).

Monthly schedule (1st, 03:00):

```
sudo cp deploy/sawmills-refresh.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sawmills-refresh.timer
systemctl list-timers sawmills-refresh        # check; logs: journalctl -u sawmills-refresh
```

The CEIDG fetch and KRS candidate discovery (Step 1 in [WORKFLOW.md](WORKFLOW.md)) are not part of `refresh.sh`. Run them in the same image when needed, for example
`docker compose --profile jobs run --rm scraper sh -c 'cd data/raw && python ../../src/ceidg_scraper/fetch_data.py --update'` (needs `CEIDG_TOKEN` in `.env`; not tested on the server).
