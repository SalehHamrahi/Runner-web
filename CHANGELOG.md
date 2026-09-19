## 1.0.0-rc3

- Fixed comparison progress bars in Match Intelligence and Tactics so Team A/Team B values are visibly color-filled according to their relative share.
- Added subtle theme-aware glow/border treatment to the filled segments.

# Changelog

## 1.0.0-rc2

- Reworked project documentation into a single public README in English and Persian.
- Removed internal development milestone documents and milestone wording from public-facing project text.
- Added a drop-in Python plugin system with discovery, metadata inspection, manual hook execution, and isolated lifecycle hooks.
- Added plugin configuration through `plugins_enabled` and `plugins_dir`.
- Added plugin tests and CLI coverage.
- Renamed internal modules and test files to domain-oriented names such as `match_ingestion.py`, `graphics.py`, `test_match_data.py`, `test_analytics.py`, and `test_simulation.py`.
- Kept quality, release, analytics, reporting, web, and Discord functionality intact.

## 1.0.0-rc1

- Added automated quality and release checks.
- Added dependency sanity checks and clean release packaging.
