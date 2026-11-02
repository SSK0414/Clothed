from uuid import uuid4
from datetime import date, timedelta
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def register(email=None):
    email = email or f"test-{uuid4().hex}@example.com"
    response = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 201
    return response.json()["access_token"]

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_create_and_list_item_is_authenticated():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": "Test shirt", "category": "Tops",
        "subcategory": "Shirt", "colour": "Blue", "pattern": "Solid"
    }
    created = client.post("/api/items", json=payload, headers=headers)
    assert created.status_code == 201
    assert created.json()["subcategory"] == "Shirt"
    item_id = created.json()["id"]
    listed = client.get("/api/items", headers=headers)
    assert any(item["id"] == item_id for item in listed.json())
    deleted = client.delete(f"/api/items/{item_id}", headers=headers)
    assert deleted.status_code == 204

def test_users_cannot_see_each_others_items():
    first_token = register()
    second_token = register()
    first_headers = {"Authorization": f"Bearer {first_token}"}
    second_headers = {"Authorization": f"Bearer {second_token}"}
    created = client.post("/api/items", json={"name":"Private coat","category":"Outerwear"}, headers=first_headers)
    assert created.status_code == 201
    assert client.get("/api/items", headers=second_headers).json() == []
    assert client.get(f"/api/items/{created.json()['id']}", headers=second_headers).status_code == 404


def test_recommendations_use_only_the_signed_in_users_wardrobe():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    top = client.post("/api/items", json={
        "name": "White tee", "category": "Tops", "colour": "White", "style": "Casual"
    }, headers=headers).json()
    bottom = client.post("/api/items", json={
        "name": "Blue jeans", "category": "Bottoms", "colour": "Blue", "style": "Casual"
    }, headers=headers).json()
    response = client.get("/api/outfits/recommendations?occasion=Casual", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recommendations"]
    recommended_ids = set(data["recommendations"][0]["item_ids"])
    assert recommended_ids == {top["id"], bottom["id"]}

def test_ai_config_is_authenticated():
    assert client.get("/api/ai/config").status_code == 401
    token = register()
    response = client.get("/api/ai/config", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["provider"] in {"ollama", "openai"}


def test_item_details_can_be_updated():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/items", json={
        "name": "Old name", "category": "Tops", "colour": "Blue"
    }, headers=headers)
    item_id = created.json()["id"]
    updated = client.patch(f"/api/items/{item_id}", json={
        "name": "Updated shirt", "colour": "White", "subcategory": "Oxford shirt"
    }, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated shirt"
    assert updated.json()["colour"] == "White"
    assert updated.json()["subcategory"] == "Oxford shirt"


def test_item_favourite_and_purchase_price_are_persisted():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/items", json={
        "name": "Canvas sneakers", "category": "Footwear", "purchase_price": 2400
    }, headers=headers)
    assert created.status_code == 201
    item_id = created.json()["id"]
    updated = client.patch(f"/api/items/{item_id}", json={"is_favorite": True}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["is_favorite"] is True
    assert updated.json()["purchase_price"] == 2400

def test_outfit_favourite_and_repeat_check():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    top = client.post("/api/items", json={"name": "Tee", "category": "Tops"}, headers=headers).json()
    bottom = client.post("/api/items", json={"name": "Jeans", "category": "Bottoms"}, headers=headers).json()
    outfit = client.post("/api/outfits", json={
        "name": "Everyday", "item_ids": [top["id"], bottom["id"]]
    }, headers=headers).json()
    updated = client.patch(f"/api/outfits/{outfit['id']}", json={"is_favorite": True}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["is_favorite"] is True
    check = client.get(f"/api/outfits/{outfit['id']}/repeat-check", headers=headers)
    assert check.status_code == 200
    assert check.json()["wear_count"] == 0

def test_analytics_returns_item_usage_and_favourite_counts():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    item = client.post("/api/items", json={
        "name": "Linen shirt", "category": "Tops", "purchase_price": 1200, "is_favorite": True
    }, headers=headers)
    assert item.status_code == 201
    result = client.get("/api/analytics", headers=headers)
    assert result.status_code == 200
    assert result.json()["favorite_item_count"] >= 1
    assert any(x["item_id"] == item.json()["id"] for x in result.json()["item_stats"])


def test_weather_aware_recommendations_accept_supported_context():
    token = register()
    headers = {"Authorization": f"Bearer {token}"}
    top = client.post("/api/items", json={"name": "Tee", "category": "Tops"}, headers=headers).json()
    bottom = client.post("/api/items", json={"name": "Trousers", "category": "Bottoms"}, headers=headers).json()
    outer = client.post("/api/items", json={"name": "Jacket", "category": "Outerwear"}, headers=headers).json()
    response = client.get("/api/outfits/recommendations?weather=cold", headers=headers)
    assert response.status_code == 200
    assert response.json()["recommendations"]
    assert any("Cold-weather preference" in reason for reason in response.json()["recommendations"][0]["reasons"])
    invalid = client.get("/api/outfits/recommendations?weather=snowstorm", headers=headers)
    assert invalid.status_code == 400


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_auth_registration_login_duplicate_and_protected_routes():
    email = f"Mixed-{uuid4().hex}@example.com"
    created = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
    assert created.status_code == 201
    assert created.json()["user"]["email"] == email.lower()
    assert client.post("/api/auth/register", json={"email": email.upper(), "password": "password-123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    login = client.post("/api/auth/login", json={"email": email, "password": "password-123"})
    assert login.status_code == 200
    assert client.get("/api/auth/me", headers=auth(login.json()["access_token"])).json()["email"] == email.lower()
    for path in ("/api/auth/me", "/api/items", "/api/outfits", "/api/wears", "/api/analytics", "/api/ai/config"):
        assert client.get(path).status_code == 401


def test_item_crud_validation_filters_and_owner_isolation():
    first, second = auth(register()), auth(register())
    item = client.post("/api/items", headers=first, json={
        "name": "Rain coat", "category": "Outerwear", "colour": "Green", "purchase_price": 3400
    })
    assert item.status_code == 201
    item_id = item.json()["id"]
    assert client.get(f"/api/items/{item_id}", headers=first).json()["purchase_price"] == 3400
    assert client.get("/api/items?category=Outerwear&q=rain", headers=first).json()[0]["id"] == item_id
    assert client.get(f"/api/items/{item_id}", headers=second).status_code == 404
    assert client.patch(f"/api/items/{item_id}", headers=second, json={"is_favorite": True}).status_code == 404
    assert client.delete(f"/api/items/{item_id}", headers=second).status_code == 404
    assert client.post("/api/items", headers=first, json={"name": "Bad price", "category": "Tops", "purchase_price": -1}).status_code == 422
    assert client.delete(f"/api/items/{item_id}", headers=first).status_code == 204
    assert client.get(f"/api/items/{item_id}", headers=first).status_code == 404


def test_outfit_crud_rejects_foreign_items_and_scopes_ownership():
    first, second = auth(register()), auth(register())
    a = client.post("/api/items", headers=first, json={"name": "Tee", "category": "Tops"}).json()
    b = client.post("/api/items", headers=first, json={"name": "Skirt", "category": "Bottoms"}).json()
    foreign = client.post("/api/items", headers=second, json={"name": "Private", "category": "Bottoms"}).json()
    assert client.post("/api/outfits", headers=first, json={"name": "Invalid", "item_ids": [a["id"], foreign["id"]]}).status_code == 400
    outfit = client.post("/api/outfits", headers=first, json={"name": "Weekend", "item_ids": [a["id"], b["id"]]})
    assert outfit.status_code == 201
    outfit_id = outfit.json()["id"]
    assert client.get("/api/outfits", headers=first).json()[0]["id"] == outfit_id
    assert client.patch(f"/api/outfits/{outfit_id}", headers=second, json={"name": "Hijack"}).status_code == 404
    assert client.get(f"/api/outfits/{outfit_id}/repeat-check", headers=second).status_code == 404
    assert client.delete(f"/api/outfits/{outfit_id}", headers=second).status_code == 404
    updated = client.patch(f"/api/outfits/{outfit_id}", headers=first, json={"name": "Weekend revised"})
    assert updated.status_code == 200 and updated.json()["name"] == "Weekend revised"
    assert client.delete(f"/api/outfits/{outfit_id}", headers=first).status_code == 204
    assert client.get(f"/api/outfits/{outfit_id}/repeat-check", headers=first).status_code == 404


def test_wear_logs_repeat_check_and_recommendations_deprioritize_recent_outfit():
    token = register(); headers = auth(token)
    top = client.post("/api/items", headers=headers, json={"name": "Tee", "category": "Tops"}).json()
    bottom = client.post("/api/items", headers=headers, json={"name": "Jeans", "category": "Bottoms"}).json()
    outfit = client.post("/api/outfits", headers=headers, json={"name": "Daily", "item_ids": [top["id"], bottom["id"]]}).json()
    other = client.post("/api/outfits", headers=headers, json={"name": "Alt", "item_ids": [top["id"], bottom["id"]]}).json()
    foreign_headers = auth(register())
    foreign_item = client.post("/api/items", headers=foreign_headers, json={"name": "Their tee", "category": "Tops"}).json()
    foreign_outfit = client.post("/api/outfits", headers=foreign_headers, json={"name": "Other", "item_ids": [foreign_item["id"]]})
    assert foreign_outfit.status_code == 201
    assert client.post("/api/wears", headers=headers, json={"worn_on": str(date.today()), "outfit_id": foreign_outfit.json()["id"]}).status_code == 400
    assert client.post("/api/wears", headers=headers, json={"worn_on": str(date.today()), "outfit_id": 999999}).status_code == 400
    log = client.post("/api/wears", headers=headers, json={"worn_on": str(date.today()), "outfit_id": outfit["id"], "note": "Sunny"})
    assert log.status_code == 201 and log.json()["outfit"]["id"] == outfit["id"]
    check = client.get(f"/api/outfits/{outfit['id']}/repeat-check", headers=headers).json()
    assert check["wear_count"] == 1 and check["days_since_last_wear"] == 0 and check["repeat_warning"] is True
    assert client.get("/api/wears", headers=headers).json()[0]["id"] == log.json()["id"]
    recs = client.get("/api/outfits/recommendations", headers=headers).json()["recommendations"]
    assert recs and set(recs[0]["item_ids"]) == {top["id"], bottom["id"]}
    assert recs[0]["recently_worn"] is True
    old = client.post("/api/wears", headers=headers, json={"worn_on": str(date.today() - timedelta(days=9)), "outfit_id": other["id"]})
    assert old.status_code == 201


def test_analytics_cost_per_wear_and_favorites_are_account_scoped():
    headers = auth(register())
    top = client.post("/api/items", headers=headers, json={"name": "Priced tee", "category": "Tops", "purchase_price": 1200, "is_favorite": True}).json()
    bottom = client.post("/api/items", headers=headers, json={"name": "Unpriced jeans", "category": "Bottoms"}).json()
    outfit = client.post("/api/outfits", headers=headers, json={"name": "Look", "item_ids": [top["id"], bottom["id"]]}).json()
    client.patch(f"/api/outfits/{outfit['id']}", headers=headers, json={"is_favorite": True})
    client.post("/api/wears", headers=headers, json={"worn_on": str(date.today()), "outfit_id": outfit["id"]})
    client.post("/api/wears", headers=headers, json={"worn_on": str(date.today() - timedelta(days=1)), "outfit_id": outfit["id"]})
    stats = client.get("/api/analytics", headers=headers).json()
    by_id = {item["item_id"]: item for item in stats["item_stats"]}
    assert by_id[top["id"]]["wear_count"] == 2 and by_id[top["id"]]["cost_per_wear"] == 600
    assert by_id[bottom["id"]]["cost_per_wear"] is None
    assert stats["favorite_item_count"] == 1 and stats["favorite_outfit_count"] == 1
    assert stats["repeated_outfits"][0]["wear_count"] == 2
    assert client.get("/api/analytics", headers=auth(register())).json()["item_count"] == 0


def test_upload_validation_and_file_serving(tmp_path, monkeypatch):
    import app.main as api
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path)
    headers = auth(register())
    assert client.post("/api/uploads", files={"file": ("x.png", b"x", "image/png")}).status_code == 401
    assert client.post("/api/uploads", headers=headers, files={"file": ("x.txt", b"x", "text/plain")}).status_code == 400
    oversized = client.post("/api/uploads", headers=headers, files={"file": ("large.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")})
    assert oversized.status_code == 413
    saved = client.post("/api/uploads", headers=headers, files={"file": ("shirt.png", b"png bytes", "image/png")})
    assert saved.status_code == 201
    filename = Path(saved.json()["image_url"]).name
    assert (tmp_path / filename).read_bytes() == b"png bytes"


def test_ai_provider_routing_errors_and_fenced_json(monkeypatch):
    import app.main as api
    token = register(); headers = auth(token)
    image = ("shirt.png", b"image", "image/png")
    payload = {"name": "Blue shirt", "category": "Tops", "confidence": 0.9}
    called = []
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setattr(api, "_analyse_with_ollama", lambda data, kind: called.append("ollama") or payload)
    monkeypatch.setattr(api, "_analyse_with_openai", lambda data, kind: called.append("openai") or payload)
    response = client.post("/api/ai/analyze", headers=headers, files={"file": image})
    assert response.status_code == 200 and called == ["ollama"]
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert client.post("/api/ai/analyze", headers=headers, files={"file": image}).status_code == 200
    assert called[-1] == "openai"
    monkeypatch.setenv("AI_PROVIDER", "unknown")
    assert client.post("/api/ai/analyze", headers=headers, files={"file": image}).status_code == 503
    assert client.post("/api/ai/analyze", headers=headers, files={"file": ("x.png", b"", "image/png")}).status_code == 400
    assert client.post("/api/ai/analyze", headers=headers, files={"file": ("x.png", b"x", "text/plain")}).status_code == 400
    assert api._extract_json('```json\n{"name":"tee"}\n```') == {"name": "tee"}


def test_outfit_extraction_saves_clothing_only_crops_and_uses_segment_categories(tmp_path, monkeypatch):
    import app.main as api
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(api, "_extract_garment_crops", lambda _: [
        ("Tops", "Top", b"top-crop"), ("Bottoms", "Pants", b"pants-crop")
    ])
    monkeypatch.setattr(api, "_analyse_clothing_image", lambda *_: {
        "name": "AI guess", "category": "Other", "confidence": 0.9, "colour": "Blue"
    })
    response = client.post("/api/ai/extract-outfit", headers=auth(register()), files={"file": ("outfit.jpg", b"photo", "image/jpeg")})
    assert response.status_code == 200
    garments = response.json()["garments"]
    assert [(g["analysis"]["category"], g["analysis"]["subcategory"]) for g in garments] == [("Tops", "Top"), ("Bottoms", "Pants")]
    assert sorted(path.read_bytes() for path in tmp_path.iterdir()) == [b"pants-crop", b"top-crop"]


def test_outfit_extraction_requires_auth_and_a_supported_photo(monkeypatch):
    assert client.post("/api/ai/extract-outfit", files={"file": ("x.jpg", b"x", "image/jpeg")}).status_code == 401
    headers = auth(register())
    assert client.post("/api/ai/extract-outfit", headers=headers, files={"file": ("x.txt", b"x", "text/plain")}).status_code == 400
    assert client.post("/api/ai/extract-outfit", headers=headers, files={"file": ("x.jpg", b"", "image/jpeg")}).status_code == 400


def test_v06_to_v07_migration_is_safe_and_idempotent(tmp_path):
    db_path = tmp_path / "v06.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("CREATE TABLE clothing_items (id INTEGER PRIMARY KEY); CREATE TABLE outfits (id INTEGER PRIMARY KEY); INSERT INTO clothing_items VALUES (1); INSERT INTO outfits VALUES (1);")
    backend = Path(__file__).resolve().parents[1]
    script = backend / "migrate_v06_to_v07.py"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": str(backend)}
    for _ in range(2):
        result = subprocess.run([sys.executable, str(script)], cwd=backend, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(db_path) as db:
        items = {row[1]: row for row in db.execute("PRAGMA table_info(clothing_items)")}
        outfits = {row[1]: row for row in db.execute("PRAGMA table_info(outfits)")}
        assert {"purchase_price", "is_favorite"} <= items.keys()
        assert "is_favorite" in outfits
        assert db.execute("SELECT is_favorite FROM clothing_items").fetchone()[0] == 0
        assert db.execute("SELECT is_favorite FROM outfits").fetchone()[0] == 0
