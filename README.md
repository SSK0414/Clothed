# cloth(ed) — v0.7 Wardrobe Intelligence

Responsive personal wardrobe app with accounts, Ollama/OpenAI image recognition, item management, outfit recommendations, wear diary, visual outfit canvas and wardrobe analytics.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Default AI is local Ollama + Gemma 4 E4B:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
```

Run `ollama pull gemma4:e4b`, ensure Ollama is running, then start the API:

```bash
uvicorn app.main:app --reload --port 8001
```

### Frontend

From the project root in another terminal:

```bash
python -m http.server 8000
```

Open http://localhost:8000.

## v0.7 features

- Mark wardrobe items and saved outfits as favourites.
- Favourite-only wardrobe filter.
- Enter purchase price for each item (optional).
- Item-level wear counts and estimated cost-per-wear.
- Least-worn and repeated-outfit insights on the overview.
- Repeat check when selecting an outfit to log; shows total wears and last-worn date, with a recent-repeat warning.
- Weather-aware recommendation context: hot, mild, cold or rainy, alongside occasion. Weather suggestions are heuristic and do not claim to know live weather or fabric water resistance.
- Existing v0.6 item editing, photo replacement, attribute filters and drag-and-drop outfit canvas remain.
- Existing v0.5 local Ollama/OpenAI provider switching remains; Ollama is default.

## Database migration from v0.6

**Back up your database first.** For an existing v0.6 database, run from the backend directory before starting the v0.7 API:

```bash
python migrate_v06_to_v07.py
```

The migration adds `purchase_price` and `is_favorite` to `clothing_items`, and `is_favorite` to `outfits`. It supports SQLite and PostgreSQL and preserves existing records. Fresh installs do not need the migration.

## Cost-per-wear

Cost per wear = entered purchase price ÷ number of wear-log entries containing that item. It is only calculated when both price and wear history exist. Amounts are displayed with ₹ as the interface's current display currency; enter prices consistently in INR for meaningful results.

## Weather context

Weather is a manual preference selector, not a live weather feed. Cold-weather suggestions favour outfits with an outer layer; hot-weather suggestions favour lighter combinations; rainy-day suggestions ensure footwear is included but do not assume it is waterproof. Scores are rule-based compatibility estimates, not AI confidence.

This remains a development prototype. Before public deployment, add HTTPS, secure sessions, token revocation, rate limiting, private image storage, image scanning, robust migrations, backups and privacy/retention controls.
