# Dynamic collaboration map — minimal installation

This add-on is intentionally separate from the existing publication-map code.

## What it does

`data/publications.json`
→ `scripts/update_collaborations.py`
→ OpenAlex paper-level authorships
→ co-author institutions as listed on each paper
→ institution coordinates
→ `data/collaborations.json`
→ interactive D3 world map

The browser never calls OpenAlex. It only reads the generated local JSON file.

## Files to add

Copy these files into the same paths in the website repository:

- `assets/js/collaboration-map.js`
- `assets/css/collaboration-map.css`
- `scripts/update_collaborations.py`
- `data/collaboration_overrides.json`
- `data/collaborations.json` (initial harmless empty seed)

Then make the three tiny `index.html` edits shown in `INDEX_EDITS.txt`.

## Automatic updates

If you ALREADY have a workflow that runs:

```bash
python scripts/update_publications.py
```

add exactly one line immediately after it:

```bash
python scripts/update_collaborations.py
```

and make sure `data/collaborations.json` is included in the files the workflow commits.

If you do NOT currently have the publication workflow, a ready-made example is included at:

`.github/workflows/update-publications.yml`

It runs weekly on Monday and can also be run manually from the Actions tab.

## Manual refresh

From the repository root:

```bash
pip install -r requirements-publications.txt
python scripts/update_publications.py
python scripts/update_collaborations.py
```

That is all.

## Corrections / edge cases

OpenAlex resolves the affiliation written on each paper to an institution. If it ever assigns one incorrectly, do NOT edit the map JavaScript.

Edit only:

`data/collaboration_overrides.json`

Examples:

```json
{
  "exclude_authors": ["Example Name"],
  "exclude_institutions": ["Example Institute"],
  "institution_overrides": {
    "normalized institution name": {
      "latitude": 43.2609,
      "longitude": -79.9192,
      "city": "Hamilton",
      "country": "Canada"
    }
  }
}
```

The override key can also be the institution's OpenAlex ID.

## Optional OpenAlex settings

No API key is required for ordinary use. If desired, the updater supports:

- `OPENALEX_API_KEY`
- `OPENALEX_AUTHOR_ID`
- `OPENALEX_MAILTO`
- `COLLABORATION_AUTHOR_NAME`

The default author name is `Anastasis Kratsios`.

## Failure behavior

The updater is fail-safe. If OpenAlex is temporarily unavailable, it preserves the last successful `data/collaborations.json` instead of overwriting it with empty data.
