# watch-kb

Daily public-data watch: rain, water level, weather warnings, highway flooding, traffic news for Thailand, Bangkok metro, and 7 watched provinces.

- `fetch_sources.py` — stdlib-only fetcher. Writes `latest.md` (one page, 3 layers), `latest.json`, `daily/YYYY-MM-DD.{md,json}`, `brief.txt` (4-line push summary).
- `.github/workflows/fetch.yml` — runs 08:30 Asia/Bangkok daily (`30 1 * * *` UTC), commits data, sends ntfy push (`NTFY_TOPIC` repo secret). Manual run: Actions → fetch → Run workflow.
- Rules: every value carries source url + reported time; a source that fails is listed under "ดึงไม่ได้" never blanked; no estimates by the summariser.

Sources: ThaiWater (HII) public API, TMD forecast/warning pages, DOH news, JS100 news. Not yet: Google Flood Forecasting API (needs key), DDPM site (SPA, no API).

Consumer: Aquarium `/monitor` reads `latest.json` from raw GitHub.
