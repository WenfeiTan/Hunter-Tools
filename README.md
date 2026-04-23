# Hunter-Tools

Google X-Ray Candidate Sourcing Tool (HRBP MVP)

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Defaults are managed by `config.yaml` via Dynaconf.  
You can edit `config.yaml` to change global defaults without changing code.

## Run

Interactive mode (recommended for non-technical users):

```bash
hunter-tools --interactive
```

Interactive mode only asks business-facing fields (`job_title`, `location`, `yoe`, mode choices, keywords, pagination, output).
Advanced runtime settings are auto-loaded from `config.yaml`:
- `delay_seconds`
- `timeout_seconds`
- `blocked_cooldown_seconds`
- `jitter_ratio`
- `show_browser`
- `fail_fast`
- `raw_output_dir`

Parameterized mode:

```bash
hunter-tools \
  --job-title HRBP \
  --location Frankfurt \
  --yoe 5 \
  --title-alias-mode core \
  --location-mode expanded \
  --args Mandarin "employee relations" \
  --show-browser \
  --raw-output-dir outputs/raw_pages \
  --output outputs/candidates.csv \
  --debug
```

## Parameter Guide

Required:
- `--job-title`: target role, e.g. `HRBP`
- `--location`: target geo, e.g. `Frankfurt`
- `--yoe`: years of experience (used in scoring, not recall filtering)

Query control (granular):
- `--title-alias-mode off|core|broad`  
  `off`: only use your exact `job-title`  
  `core`: include a few aliases  
  `broad`: include more aliases (longer query, higher recall)
- `--location-mode strict|expanded|country_only`  
  `strict`: only input location  
  `expanded`: city + expanded terms (default)  
  `country_only`: only country-level term (widest recall)

Scoring control:
- `--args ...`: custom scoring keywords (no longer used to constrain query)

Browser acquisition control (Selenium only):
- `--show-browser`: show browser when using selenium
- `--pages-per-query`: pages to fetch per query
- `--page-size`: results per page
- `--delay-seconds`: base delay between page fetches
- `--timeout-seconds`: page load timeout in seconds

Anti-block / resilience:
- `--blocked-cooldown-seconds`: stronger cooldown for `/sorry/` or 429
- `--fail-fast`: stop whole run on first query failure

Debug / output:
- `--raw-output-dir`: save raw HTML + JSON metadata before parsing (default `outputs/raw_pages`)
- `--output`: final CSV path
- `--debug`: print stage-level logs

## Scenario Presets

1. Shortest query (strong control, lowest length)
```bash
hunter-tools \
  --job-title HRBP \
  --location Frankfurt \
  --yoe 5 \
  --title-alias-mode off \
  --location-mode strict \
  --show-browser \
  --pages-per-query 1 \
  --output outputs/strict.csv \
  --debug
```

2. Balanced recall (recommended)
```bash
hunter-tools \
  --job-title HRBP \
  --location Frankfurt \
  --yoe 5 \
  --title-alias-mode core \
  --location-mode expanded \
  --args Mandarin "employee relations" \
  --pages-per-query 1 \
  --delay-seconds 8 \
  --output outputs/balanced.csv \
  --debug
```

3. Max recall (wider geo/title)
```bash
hunter-tools \
  --job-title HRBP \
  --location Frankfurt \
  --yoe 5 \
  --title-alias-mode broad \
  --location-mode country_only \
  --pages-per-query 1 \
  --delay-seconds 10 \
  --output outputs/max_recall.csv \
  --debug
```

## Project Structure

```text
src/hunter_tools/
  config.py
  models.py
  query_builder.py
  google_page.py
  selenium_client.py
  parser.py
  scorer.py
  pipeline.py
  exporter.py
  main.py
tests/
docs/
```

## MVP Coverage

- Query Builder (HRBP only)
- Google search fetch (Selenium + browser rendering)
- LinkedIn profile filtering
- Rule-based scoring (fine-grained ranking from broad recall queries)
- CSV export
