# cloth(ed) v0.7 API test report

Run date: 2026-11-01

- Backend requirements installed in an isolated Python 3.12 virtual environment.
- `pytest -q`: **18 passed**, 53 deprecation warnings, in 1.92 seconds.
- Covered registration/login, authentication, per-user data ownership, item and outfit CRUD, favourites, purchase price, wear logs, repeat checks, recommendation weather/repeat behavior, analytics and cost-per-wear, upload validation/storage, AI provider routing/error handling, fenced JSON parsing, and the v0.6-to-v0.7 SQLite migration (including rerun safety).
- AI provider calls were stubbed; no live Ollama or OpenAI service was contacted. PostgreSQL migration was not exercised.
- Warnings are from Starlette's deprecated AnyIO alias and SQLAlchemy's existing `datetime.utcnow()` model defaults.

Fix included: fenced JSON from AI responses now splits on actual newlines, so a standard ```` ```json ```` response parses correctly.

## Outfit photo extraction

- Added authenticated outfit-photo extraction tests: 20 tests pass in the updated suite.
- The garment segmentation model is mocked in tests. On first real use, the server downloads the configured local model (`mattmdjaga/segformer_b2_clothes`) and uses it to make transparent garment-only PNG crops.
