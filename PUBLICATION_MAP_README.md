# Automated publication map

This site replaces the former hard-coded **Publications and Preprints** section
with an interactive research DAG. The page reads from `data/publications.json`.

## Automated updates

The workflow `.github/workflows/update-publications.yml` runs weekly and can also
be launched manually from the GitHub Actions tab. It executes:

```bash
python scripts/update_publications.py
```

The updater uses the Google Scholar profile `9D-bHFgAAAAJ` as the primary source,
then enriches titles with Semantic Scholar/OpenAlex metadata when available. If
Scholar blocks an automated run, the script preserves the last successful JSON so
the website does not break.

Optional: add a repository secret named `SEMANTIC_SCHOLAR_API_KEY` to improve
Semantic Scholar rate limits.

## Manual corrections

Use `data/publication_overrides.json` for topic, venue, or URL corrections. Keys
are normalized paper titles, so accents and punctuation do not matter.
