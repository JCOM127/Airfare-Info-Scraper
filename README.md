# Fly Tcoma Flight Rewards Scraper

Pipeline to fetch Seats.aero availability, normalize to a data contract, and optionally upload results to Google Drive.

**Table of Contents**
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Testing](#testing)
- [CI/CD](#cicd)

---

## Overview

This project implements an ETL (Extract-Transform-Load) pipeline for flight rewards availability:

- **Extract (E):** Scrapes Seats.aero using Playwright browser automation
- **Transform (T):** Normalizes data and validates against JSON Schema contract
- **Load (L):** Uploads to Google Drive (OAuth or Service Account)

### Features

- Browser automation with Playwright for JavaScript-rendered content
- Network request interception to capture flight APIs
- Configuration-driven (no code changes needed)
- JSON Schema data contracts for data quality
- Comprehensive logging and error handling
- Unit tests with pytest
- CI/CD with GitHub Actions
- Multiple Google Drive authentication modes

---

## Prerequisites

- **Python 3.10+** (venv recommended)
- **Playwright Chromium** (auto-installed)
- **Google Drive API** (optional, for uploads)

### Installation

```bash
# Clone repository
git clone <repo>
cd fly-tcoma-scraper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright Chromium
python -m playwright install chromium
```

---

## Configuration

### config.json

Configure your search parameters in `config/config.json`:

```json
{
  "project_name": "Seats.aero Scraper",
  "env": "dev",
  "default_programs": ["AeroplanPlus"],
  "scraping_settings": {
    "headless": true,
    "timeout_ms": 60000,
    "retries": 3,
    "search_window_days": 60,
    "departure_date": "2025-12-25",
    "max_offers_per_route": 20
  },
  "routes": [
    {
      "origin": "YYZ",
      "destination": "CDG",
      "programs": ["AeroplanPlus"]
    }
  ]
}
```

**Field Reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `routes` | Array | Required | List of flight routes to search |
| `routes[].origin` | String | Required | Departure airport (IATA code) |
| `routes[].destination` | String | Required | Arrival airport (IATA code) |
| `routes[].programs` | Array | Required | Loyalty programs to search |
| `default_programs` | Array | Required | Programs used if route doesn't specify |
| `search_window_days` | Integer | Optional | Days ahead to search (default: 60) |
| `departure_date` | String | Optional | Start date (YYYY-MM-DD format) |
| `max_offers_per_route` | Integer | Optional | Max offers per route (default: 20, caps API load) |

### data_contract.json

Defines expected data structure (JSON Schema). Validates scraped data. See `config/data_contract.json` for full schema.

---

## Quick Start

### 1. Extract Flight Data

```bash
python src/scraper.py
```

**Output:** `output/run_2025-11-30T09-02-51Z.json` (raw data)

**What happens:**
- Launches headless Chromium browser
- Navigates to Seats.aero
- Intercepts flight API responses
- Filters by configured routes and programs
- Saves raw JSON with timestamp

### 2. Transform & Validate

```bash
python -m src.transform output/run_2025-11-30T09-02-51Z.json
```

**Output:** `output/run_2025-11-30T09-02-51Z_transformed.json` (normalized data)

**What happens:**
- Reads raw extraction output
- Normalizes field names and types
- Validates against data contract
- Logs schema violations (warnings only)
- Saves transformed JSON

### 3. Upload to Google Drive (Optional)

**Setup OAuth (personal account):**

```bash
export GOOGLE_CLIENT_SECRETS=~/.config/client_secret.json
export GOOGLE_TOKEN_FILE=~/.cache/fly_tcoma_drive_token.json
```

**Upload:**

```bash
python -c "
from src.loader import upload_to_drive

file_id = upload_to_drive(
    'output/run_2025-11-30T09-02-51Z_transformed.json',
    folder_id='<YOUR_FOLDER_ID>'
)
print(f'Uploaded: {file_id}')
"
```

---

## Usage

### Full Pipeline Example

```bash
#!/bin/bash
set -e

echo "=== Step 1: Extract ==="
python src/scraper.py
LATEST=$(ls -t output/run_*.json | grep -v transformed | head -1)
echo "Extracted: $LATEST"

echo "=== Step 2: Transform ==="
python -m src.transform "$LATEST"
TRANSFORMED="${LATEST%.json}_transformed.json"
echo "Transformed: $TRANSFORMED"

echo "=== Step 3: Verify ==="
jq '.flights[0]' "$TRANSFORMED"

echo "Done!"
```

### Google Drive Authentication

#### OAuth (Personal Account)

```bash
# 1. Create credentials at https://console.cloud.google.com
#    - Create OAuth 2.0 client ID (Desktop)
#    - Download JSON

# 2. Set environment variable
export GOOGLE_CLIENT_SECRETS=~/Downloads/client_secret.json

# 3. First run opens browser for authorization
python -c "from src.loader import upload_to_drive; upload_to_drive('file.json', folder_id='...')"

# Token cached to ~/.cache/fly_tcoma_drive_token.json
```

#### Service Account (Shared Drive)

```bash
# 1. Create service account at https://console.cloud.google.com
#    - Create service account
#    - Create JSON key
#    - Share Shared Drive folder with SA email

# 2. Set environment variable
export GDRIVE_SERVICE_ACCOUNT_FILE=~/service-account.json

# 3. Upload (no browser interaction)
python -c "
from src.loader import upload_to_drive
upload_to_drive(
    'file.json',
    folder_id='<FOLDER_ID>',
    drive_id='<SHARED_DRIVE_ID>'
)
"
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run specific test file
python -m pytest tests/test_scraper.py -v
```

---

## Troubleshooting

### Error: `Error: Chromium executable not found`

**Cause:** Playwright Chromium not installed

**Solution:**
```bash
python -m playwright install chromium
```

---

### Error: `429 Too Many Requests`

**Cause:** Scraping too many offers per route (hitting Seats.aero rate limit)

**Solution:** Reduce `max_offers_per_route` in `config/config.json`:

```json
{
  "max_offers_per_route": 10
}
```

---

### Error: `jsonschema.ValidationError: 'price' is a required property`

**Cause:** Scraped data doesn't match data contract (API response format changed)

**Solution:**
1. Check if Seats.aero API response format changed
2. Update `config/data_contract.json` to match new schema
3. Run transform in non-strict mode (logs warnings instead of failing)

---

### Error: `FileNotFoundError: run_*.json not found`

**Cause:** Transform file not found

**Solution:**
1. Verify extraction completed: `ls output/run_*.json`
2. Use correct filename: `python -m src.transform output/run_<EXACT_TIMESTAMP>.json`
3. Run scraper first: `python src/scraper.py`

---

### Error: `Google Drive: Invalid OAuth token`

**Cause:** OAuth token expired or revoked

**Solution:**
```bash
# Delete cached token
rm ~/.cache/fly_tcoma_drive_token.json

# Re-authenticate (opens browser)
python -c "from src.loader import upload_to_drive; upload_to_drive('file.json', folder_id='...')"
```

---

### Error: `Service Account: Permission denied`

**Cause:** Shared Drive not shared with service account email

**Solution:**
1. Get service account email: `grep "client_email" service-account.json`
2. Share Shared Drive folder with that email
3. Retry upload with `drive_id` parameter

---

### No Flights Found

**Cause:** Routes/programs not available or incorrectly configured

**Solution:**
1. Verify IATA codes: `JFK`, `CDG`, `LHR` (3 letters, uppercase)
2. Check programs exist: `AeroplanPlus`, `PointsPlus`
3. Extend search window: `"search_window_days": 60`
4. Check departure date is valid
5. Try fewer routes first to debug

---

## Architecture

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────┐
│         Configuration Layer (config.json)            │
│    Routes, programs, search window, dates            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│      Extraction (E) - scraper.py                    │
│  ├─ Launch Playwright headless browser              │
│  ├─ Navigate to Seats.aero                          │
│  ├─ Intercept fetch API requests                    │
│  ├─ Filter by configured routes & programs         │
│  └─ Implement retry logic for failures              │
└──────────────────┬──────────────────────────────────┘
                   │
              output/run_<timestamp>.json
              (Raw flight data)
                   │
┌──────────────────▼──────────────────────────────────┐
│   Data Validation (config/data_contract.json)       │
│     └─ JSON Schema validation layer                 │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│     Transformation (T) - transform.py               │
│  ├─ Normalize field names and types                 │
│  ├─ Enrich data with computed fields                │
│  ├─ Apply business logic                            │
│  └─ Log schema violations (warnings)                │
└──────────────────┬──────────────────────────────────┘
                   │
       output/run_<timestamp>_transformed.json
       (Normalized flight data)
                   │
┌──────────────────▼──────────────────────────────────┐
│       Load (L) - loader.py                          │
│  ├─ OAuth or Service Account auth                   │
│  ├─ Upload to Google Drive / Shared Drive           │
│  └─ Return file ID for tracking                     │
└──────────────────┬──────────────────────────────────┘
                   │
         Google Drive / Shared Drive
              (Cloud storage)
```

### Module Responsibilities

| Module | Responsibility | Input | Output |
|--------|-----------------|-------|--------|
| `scraper.py` | Extract flight data from Seats.aero | config.json | run_<timestamp>.json |
| `transform.py` | Normalize and validate data | run_<timestamp>.json | run_<timestamp>_transformed.json |
| `loader.py` | Upload to Google Drive | run_<timestamp>_transformed.json | File ID |
| `config.py` | Load and validate configuration | config.json | AppConfig object |
| `logger.py` | Structured logging | - | logs/app.log |
| `utils.py` | Utility functions | - | Various |

---

## Testing

### Run All Tests

```bash
python -m pytest
```

### Test Coverage

| Test File | Module | Coverage |
|-----------|--------|----------|
| `test_scraper.py` | scraper.py | Extraction, parsing, filtering |
| `test_transform.py` | transform.py | Normalization, validation |
| `test_scraper_config.py` | config.py | Config loading |
| `test_utils.py` | utils.py | Utility functions |

---

## CI/CD

### GitHub Actions Workflow

GitHub Actions automatically runs tests on every push and pull request.

**Workflow file:** `.github/workflows/ci.yml`

**What happens:**
1. Runs all unit tests with pytest
2. Validates code quality
3. Checks configuration schema
4. Fails if any test doesn't pass (prevents broken code)

### View CI/CD Results

- Navigate to repository → **Actions** tab
- See test results and logs for each run

### Local Testing Before Push

```bash
# Run tests locally to catch issues early
python -m pytest -v

# Only push if tests pass
git push origin main
```

---

## File Structure

```
fly-tcoma-scraper/
├── .gitignore
├── README.md
├── requirements.txt
├── .github/
│   └── workflows/
│       └── ci.yml
├── config/
│   ├── config.json           # User configuration
│   ├── config_schema.json    # Schema for config validation
│   └── data_contract.json    # Schema for flight data validation
├── logs/                     # Runtime logs
├── output/                   # Timestamped outputs
│   ├── run_*.json           # Raw extraction
│   └── run_*_transformed.json # Transformed data
├── src/
│   ├── __init__.py
│   ├── config.py            # Configuration loading
│   ├── loader.py            # Google Drive uploader
│   ├── logger.py            # Logging setup
│   ├── scraper.py           # Extraction
│   ├── transform.py         # Transformation
│   └── utils.py             # Utilities
└── tests/
    ├── __init__.py
    ├── test_scraper.py
    ├── test_scraper_config.py
    ├── test_transform.py
    └── test_utils.py
```

---

## ETL Practices

- **Extraction:** Seats.aero API via browser fetch, program filtering, retries
- **Transform:** Normalization + schema validation; violations logged as warnings
- **Load:** Google Drive uploader with OAuth or service account
- **Logging:** Route-level counts, transform summaries; adjust in `src/logger.py`
- **Contract:** Defined as JSON Schema in `config/data_contract.json`

---

## License

MIT

## Contributing

Pull requests welcome! Please run tests before submitting.

```bash
python -m pytest -v
```
````
