# Backend Scripts

This folder contains one-off and semi-operational scripts for LinkedIn data ingestion and enrichment.

## Scripts

### `import_linkedin_connections.py`

Imports a saved LinkedIn connections HTML page into Kizuna.

What it extracts:

- display name
- canonical LinkedIn profile URL
- LinkedIn headline
- connected-time badge text from the saved page
- avatar URL from the saved page

How it maps into Kizuna:

- `display_name`
- `given_name` / `family_name` when a simple split is possible
- `short_bio` from the LinkedIn headline
- `how_we_met = "LinkedIn connection import"`
- `notes` with import provenance and raw LinkedIn snapshot metadata
- `external_profiles` with platform `LinkedIn`
- `source_links` for provenance

Important behavior:

- dedupes by canonical LinkedIn profile URL, not by name
- is rerunnable against the same snapshot
- can update previously imported LinkedIn records in place

### `scrape_linkedin_profile_selenium.py`

Scrapes richer LinkedIn profile details using Selenium with Firefox and a reused Firefox profile.

What it extracts:

- top-card fields
  - name
  - headline
  - location
  - mutual connections text
  - mutual connections count
- experience
- education
- skills
- highest-resolution visible profile photo URL
- cached local copy of the profile photo

Outputs:

- JSON summary file
- cached profile image in the profile-photo cache directory

### `batch_scrape_linkedin_profiles.py`

Batch-scrapes LinkedIn profiles already stored in the Kizuna backend database.

What it does:

- reads `ExternalProfile` rows with platform `LinkedIn`
- joins them back to `Person`
- dedupes by canonical LinkedIn profile URL
- processes profiles in batches
- pauses a random 10-30 seconds between profiles by default
- reuses one Firefox session when healthy, but restarts it periodically
- appends one JSON line per scrape attempt so interruptions can resume cleanly
- writes a progress snapshot after every processed profile
- writes one pretty JSON file per successful scrape for easier spot-checking

Outputs:

- append-only JSONL results log
- progress JSON snapshot
- per-profile JSON files
- cached profile image in the profile-photo cache directory

Resume behavior:

- successful profiles are skipped on rerun
- errored profiles are skipped by default so a rerun does not loop forever on the same failures
- use `--retry-errors` to retry previously failed profiles
- if the process is interrupted mid-profile, that URL has no successful terminal record and will be retried on the next run
- use `--dry-run` to inspect target counts and resume state without launching Firefox

## Why Selenium + Firefox Profile

Playwright was explored first, but the working path for this machine was the exact same broad approach as the preexisting Selenium script in the other repo:

- launch real Firefox through Selenium
- pass the existing Firefox profile via `--profile=...`
- reuse the already logged-in browser state

This approach was proven working for LinkedIn in this environment, while Playwright hit compatibility issues with Firefox/profile reuse.

## How The Scraper Is Constructed

The scraper has four layers:

1. Browser bootstrap

- launches Firefox with an existing profile
- applies a few basic browser preferences mirroring the older working script
- optionally runs headless

2. Page access checks

- opens the requested profile URL
- waits for `main`
- verifies LinkedIn did not redirect to login, checkpoint, or authwall

3. Expansion step

- scans visible buttons/role-buttons
- clicks text patterns like `show more`, `show all`, `see more`, and `… more`
- repeats for several rounds until nothing else expands

4. Section extraction

- top card is parsed from the main page text
- experience, education, and skills are scraped from LinkedIn detail pages:
  - `/details/experience/`
  - `/details/education/`
  - `/details/skills/`
- section text is trimmed before LinkedIn viewer/footer noise
- timeline-style sections are split into entries by date lines
- skills are filtered to remove category labels and endorsement boilerplate
- the profile photo is chosen from `main img` elements by looking for `profile-displayphoto` and selecting the largest visible candidate

## Learnings From Testing

### Self-profile test

The script was tested on a self profile first to validate the session and section structure.

What worked well:

- experience content was captured with descriptions
- education content was clean
- skills content was usable after filtering endorsement text
- top-card location was extractable
- profile photo caching worked

### Connection-profile test

The script was also tested on another LinkedIn profile to confirm it generalizes beyond self pages.

What worked well:

- mutual-connections text is exposed in the top card
- mutual-connections count can be parsed from that text
- location extraction still works
- profile photo caching still works

### Structural observations

LinkedIn detail pages are not especially friendly to stable selectors:

- the detail content is often under `main#workspace`
- class names are heavily obfuscated and unstable
- useful content and irrelevant content often live in the same broad wrapper
- viewer suggestions, language controls, and footer text appear below the real section content

Because of that, the current extractor relies on:

- section-page text wrappers
- stop markers such as:
  - `Profile language`
  - `Who your viewers also viewed`
  - `About`
  - `Select language`

This is more resilient than brittle class-name targeting, though still heuristic.

## Known Limitations

### Grouped experience roles

Profiles with nested roles under one company are not fully normalized yet. The current parser can flatten these imperfectly.

Example pattern that is still rough:

- company
- total tenure
- role A + role A dates
- role B + role B dates

The scraper captures the text, but the structured `items` may not split every grouped-role profile perfectly.

### Shared Firefox profile concurrency

Do not run multiple scraper sessions in parallel against the same Firefox profile.

Observed failure modes:

- `Maximum number of active sessions`
- Marionette session creation errors

Recommended rule:

- run one Selenium scrape at a time per Firefox profile

### Browser state dependency

The script depends on a valid logged-in Firefox profile. If LinkedIn expires the session or challenges the profile, scraping will stop working until the browser profile is refreshed manually.

## Operational Guidance

Recommended workflow:

1. Log into LinkedIn manually in Firefox using the intended profile.
2. Close Firefox if necessary so Selenium can take control cleanly.
3. Run one profile scrape at a time.
4. Inspect JSON output for structural issues before scaling up.
5. Only then batch over stored LinkedIn URLs.

## Safety / Privacy Notes

This README intentionally does not include:

- local machine profile paths beyond general discussion
- credentials
- cookies
- private profile contents
- any instruction to bypass login or platform controls

Keep any batch usage respectful, low-rate, and manually supervised.
