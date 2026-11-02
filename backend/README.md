# cloth(ed) API — v0.7

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Default image recognition uses Ollama + `gemma4:e4b`. Keep `AI_PROVIDER=ollama` for local processing, or configure the optional OpenAI provider with `AI_PROVIDER=openai` and `OPENAI_API_KEY`.

### Extract clothes from an outfit photo

In **Add to your wardrobe**, upload a clear photo of a person wearing an outfit and choose **Extract clothes from outfit**. The API downloads the local segmentation model on its first use, removes the person, skin and background, then saves a transparent crop for every detected garment. Review a crop or choose **Add all** to create separate wardrobe items. This needs the image-segmentation packages in `requirements.txt` and network access once to fetch the model weights.

Run:

```bash
uvicorn app.main:app --reload --port 8001
```

## Migration from v0.6

Back up the database, then run from this directory before starting the updated API:

```bash
python migrate_v06_to_v07.py
```

Adds nullable `clothing_items.purchase_price` and non-null `is_favorite` columns to `clothing_items` and `outfits`. Supports SQLite and PostgreSQL. Fresh databases are created from the updated SQLAlchemy models and need no migration.

## v0.7 API additions

| Method | Endpoint | Purpose |
|---|---|---|
| PATCH | `/api/outfits/{outfit_id}` | Update outfit name/favourite status |
| GET | `/api/outfits/{outfit_id}/repeat-check` | Wear count, last worn and recent-repeat warning |
| GET | `/api/analytics` | Per-item wear counts, cost-per-wear, favourites, least-worn and repeated outfits |
| GET | `/api/outfits/recommendations?weather=cold` | Weather-context outfit recommendations |

All endpoints require authentication and are scoped to the signed-in account. `purchase_price` is optional and must be a non-negative number. Cost-per-wear is calculated only when an item has both a purchase price and at least one wear-log entry.
