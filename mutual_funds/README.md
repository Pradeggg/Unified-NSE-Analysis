# Mutual Funds Workspace

Created: 2026-08-06

This folder now contains the small-cap mutual-fund source bundle and the Agent Adda comparison work.

## Agent Adda Small Cap Portfolio Framing

The operating vehicle is the Agent Adda Small Cap Portfolio: an internal paper/model portfolio owned by Mahesh Binjola and Pradeep Gorai. The small-cap fund policy file is retained as a governance rulebook and historical path name, but the current approach is portfolio-first rather than a formal fund. External mutual-fund holdings in this folder are used only as source evidence and institutional-overlap signals.

## Structure

- `raw/local_downloads/` - manually downloaded Kotak and Nippon PDFs from Downloads.
- `raw/official_downloads/` - live AMC-hosted documents downloaded for peer small-cap funds.
- `working/` - unpacked/intermediate source files.
- `extracted/` - holdings and metadata CSV/JSON files ready for comparison.
- `reports/` - Agent Adda small-cap and Kotak comparison HTML/CSV reports copied from `reports/`.
- `manifests/` - source manifest and download status.

## Current Extraction Coverage

Full/usable holdings CSVs are currently available for:

- Kotak Small Cap Fund, as of 2025-02-28.
- Nippon India Small Cap Fund top disclosed holdings, as of 2025-02-28.
- DSP Small Cap Fund, as of 2026-06-30.
- Motilal Oswal Small Cap Fund, as of 2026-06-30.

Other downloaded PDFs are saved as source evidence but still need section-level parsing before they should be used in a holdings consensus model.

## Notes

- Existing files under `reports/` were copied here, not removed, so existing latest-report paths remain intact.
- HDFC and Tata required browser-style headers for direct document download.
- Bandhan and Sundaram official pages were source-located but their current direct file endpoints were not cleanly exposed during this pass.
- Treat factsheets and one-pagers as partial holdings evidence unless full scheme portfolio tables can be extracted.
