# Automated publication map

This site replaces the former hard-coded **Publications and Preprints** section
with an interactive research DAG. The page reads from `data/publications.json`.

## Automated updates

The workflow `.github/workflows/update-publications.yml` runs weekly and can also
be launched manually from the GitHub Actions tab. It executes:

```bash
python scripts/update_publications.py
```

The updater combines:

1. the Google Scholar profile `9D-bHFgAAAAJ`, for the canonical publication list
   and citation counts when Scholar is reachable;
2. the arXiv author search `au:Kratsios_A`, for arXiv identifiers, abstracts,
   subjects, and missing preprints;
3. optional Semantic Scholar/OpenAlex enrichment for venues, DOI/URLs, abstracts,
   and citation counts.

The arXiv subject classes are used as the first structured signal for automatic
classification into the website's high-level DAG:

- AI Theory
  - Universal Neural Approximation
  - Statistical Learning Theory
  - Reasoning & Computation
  - Operator Learning
  - Geometric Deep Learning
- Applications
  - PDEs
  - Control & Optimization
  - Games & BSDEs
  - Finance
  - Misc.

If Scholar or another source blocks an automated run, the script preserves the
last successful JSON so the website does not break. If arXiv is reachable, the
update can still succeed even when Scholar is blocked.

Optional: add a repository secret named `SEMANTIC_SCHOLAR_API_KEY` to improve
Semantic Scholar rate limits.

## Manual corrections

Use `data/publication_overrides.json` for topic, venue, URL, or arXiv-category
corrections. Keys are normalized paper titles, so accents and punctuation do not
matter.
