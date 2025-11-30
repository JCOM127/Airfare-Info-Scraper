## Fly Tcoma Flight Rewards Scraper

Pipeline to fetch Seats.aero availability, normalize to a data contract, and optionally upload results to Google Drive.

### Prerequisites
- Python 3.10+ (venv recommended)
- `pip install -r requirements.txt`
- Playwright chromium (if not installed: `python -m playwright install chromium`)

### Config
- Edit `config/config.json` for routes, programs, search window, departure date.
- Data contract lives in `config/data_contract.json` (JSON Schema).

### Run scraper (E)
```bash
python src/scraper.py
```
Output: `output/run_<timestamp>.json`

### Transform (T)
```bash
python -m src.transform output/run_<timestamp>.json
```
Output: `output/run_<timestamp>_transformed.json` and schema validation log warnings if mismatches.

### Load to Google Drive (L)
Two auth modes (loader auto-picks OAuth first):
1) OAuth (your account):
   - Set `GOOGLE_CLIENT_SECRETS=path/to/client_secret.json`
   - Optional: `GOOGLE_TOKEN_FILE=path/to/token.json` (default `~/.cache/fly_tcoma_drive_token.json`)
   - First run opens browser to authorize.
2) Service account (requires Shared Drive):
   - Set `GDRIVE_SERVICE_ACCOUNT_FILE` (or `GOOGLE_APPLICATION_CREDENTIALS`) to the SA JSON
   - Share a Shared Drive folder with the SA; pass `drive_id` and `folder_id`.

Upload example:
```bash
python - <<'PY'
from src.loader import upload_to_drive
fid = upload_to_drive("output/run_<timestamp>_transformed.json",
                      folder_id="<FOLDER_ID>",  # required
                      drive_id="<SHARED_DRIVE_ID>" )  # optional unless using Shared Drive
print(fid)
PY
```

### Tests
```bash
python -m pytest
```
Tests cover parsing helpers, transform + schema validation, and config load.

### Notes / ETL practices
- Extraction: Seats.aero API via browser `fetch`, program filtering, retries.
- Transform: normalization + schema validation against `config/data_contract.json`; logs mismatches.
- Load: Google Drive uploader with OAuth or service account + Shared Drive.
- Logging: route-level counts, transform summaries; adjust in `src/logger.py`.
