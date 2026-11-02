import os
from dotenv import load_dotenv
load_dotenv()
import base64
import json
import asyncio
import io
from functools import lru_cache
from pathlib import Path
from uuid import uuid4
from datetime import datetime, date, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func
from .database import Base, engine, get_db
from . import models, schemas

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

app = FastAPI(title="cloth(ed) API", description="Personal wardrobe, outfits, wear diary and AI clothing recognition.", version="0.7.0")
origins = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "http://localhost:8000").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

def create_token(user_id: int):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES)}, JWT_SECRET, algorithm="HS256")

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user

def owned_item(db: Session, item_id: int, user_id: int):
    item = db.scalar(select(models.ClothingItem).where(models.ClothingItem.id == item_id, models.ClothingItem.owner_id == user_id))
    if not item: raise HTTPException(404, "Wardrobe item not found.")
    return item

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "clothed-api", "version": "0.7.0"}

@app.post("/api/auth/register", response_model=schemas.TokenOut, status_code=201)
def register(payload: schemas.AuthRegister, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = models.User(email=email, password_hash=password_hash.hash(payload.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user.id), "user": user}

@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(payload: schemas.AuthLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if not user or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return {"access_token": create_token(user.id), "user": user}

@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(current_user)):
    return user

@app.post("/api/uploads", status_code=201)
async def upload_image(file: UploadFile = File(...), user: models.User = Depends(current_user)):
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if file.content_type not in allowed: raise HTTPException(400, "Upload a JPG, PNG or WEBP image.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024: raise HTTPException(413, "Image must be 5 MB or smaller.")
    filename = f"user-{user.id}-{uuid4().hex}{allowed[file.content_type]}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return {"image_url": f"/uploads/{filename}"}



AI_INSTRUCTIONS = """
You are the clothing cataloguer for cloth(ed), a personal digital wardrobe.
Inspect the supplied image and return ONLY one valid JSON object with these keys:
name, category, subcategory, colour, secondary_colour, pattern, material,
style, occasion, description, confidence, notes.
category must be one of: Tops, Bottoms, Outerwear, Footwear, Accessories, Other.
subcategory should be a useful specific type such as T-shirt, shirt, jeans, trousers,
sneakers, handbag, dress, kurta, blazer, etc.
Use concise human-readable values. Use null when an attribute cannot be determined.
Do not guess fabric/material from appearance alone; use null or "Unknown" if uncertain.
Do not infer brand, price, product code, gender, or identity.
confidence is a number from 0 to 1 reflecting confidence in the overall item/category.
name should be a short editable catalogue title.
description should be one short visual description. notes may mention uncertainty.
If the image is not clearly clothing, set category to Other, confidence below 0.35,
and explain the issue in notes.
"""

GARMENT_SEGMENTS = (
    ((1,), "Accessories", "Hat"), ((4,), "Tops", "Top"), ((5,), "Bottoms", "Skirt"),
    ((6,), "Bottoms", "Pants"), ((7,), "Other", "Dress"), ((8,), "Accessories", "Belt"),
    ((9, 10), "Footwear", "Shoes"), ((16,), "Accessories", "Bag"), ((17,), "Accessories", "Scarf"),
)

@lru_cache(maxsize=1)
def _garment_segmenter():
    try:
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
    except ImportError as exc:
        raise RuntimeError("Clothing extraction needs the image-segmentation dependencies. Run pip install -r requirements.txt.") from exc
    model_id = os.getenv("GARMENT_SEGMENTATION_MODEL", "mattmdjaga/segformer_b2_clothes")
    return AutoImageProcessor.from_pretrained(model_id), SegformerForSemanticSegmentation.from_pretrained(model_id)

def _extract_garment_crops(data: bytes):
    try:
        import numpy as np
        import torch
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Clothing extraction needs the image-segmentation dependencies. Run pip install -r requirements.txt.") from exc
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    processor, model = _garment_segmenter()
    inputs = processor(images=image.convert("RGB"), return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    labels = torch.nn.functional.interpolate(logits, size=(image.height, image.width), mode="bilinear", align_corners=False).argmax(dim=1)[0].cpu().numpy()
    crops = []
    for label_ids, category, subcategory in GARMENT_SEGMENTS:
        mask = np.isin(labels, label_ids)
        if not mask.any():
            continue
        ys, xs = mask.nonzero()
        left, top = max(0, xs.min() - 8), max(0, ys.min() - 8)
        right, bottom = min(image.width, xs.max() + 9), min(image.height, ys.max() + 9)
        if (right - left) * (bottom - top) < 400:
            continue
        alpha = Image.fromarray((mask[top:bottom, left:right] * 255).astype("uint8"))
        crop = image.crop((left, top, right, bottom))
        crop.putalpha(alpha)
        output = io.BytesIO()
        crop.save(output, format="PNG")
        crops.append((category, subcategory, output.getvalue()))
    return crops

def _extract_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(raw)

def _analyse_with_ollama(data: bytes, content_type: str):
    import urllib.request
    import urllib.error
    model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{
            "role": "user",
            "content": AI_INSTRUCTIONS,
            "images": [base64.b64encode(data).decode("utf-8")]
        }],
        "options": {"temperature": 0.1}
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Cannot reach Ollama. Start Ollama and confirm it is listening at "
            f"{base_url}. Then pull the model with: ollama pull {model}"
        ) from exc
    content = result.get("message", {}).get("content", "")
    if not content:
        raise ValueError("Ollama returned an empty response.")
    return _extract_json(content)

def _analyse_with_openai(data: bytes, content_type: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI is selected but OPENAI_API_KEY is not configured.")
    from openai import OpenAI
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-5.5")
    client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)
    data_url = f"data:{content_type};base64,{base64.b64encode(data).decode('utf-8')}"
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": AI_INSTRUCTIONS},
            {"type": "input_image", "image_url": data_url, "detail": "high"},
        ]}],
        max_output_tokens=500,
    )
    return _extract_json(response.output_text)

def _analyse_clothing_image(data: bytes, content_type: str):
    provider = os.getenv("AI_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        parsed = _analyse_with_ollama(data, content_type)
    elif provider == "openai":
        parsed = _analyse_with_openai(data, content_type)
    else:
        raise RuntimeError("AI_PROVIDER must be either 'ollama' or 'openai'.")
    result = schemas.ClothingAnalysis.model_validate(parsed)
    if result.category not in {"Tops", "Bottoms", "Outerwear", "Footwear", "Accessories", "Other"}:
        result.category = "Other"
    return result.model_dump()

@app.get("/api/ai/config")
def ai_config(user: models.User = Depends(current_user)):
    provider = os.getenv("AI_PROVIDER", "ollama").strip().lower()
    if provider == "openai":
        return {"provider": "openai", "model": os.getenv("OPENAI_VISION_MODEL", "gpt-5.5"), "mode": "cloud"}
    return {"provider": "ollama", "model": os.getenv("OLLAMA_MODEL", "gemma4:e4b"), "mode": "local"}

@app.post("/api/ai/analyze", response_model=schemas.ClothingAnalysis)
async def analyze_clothing(file: UploadFile = File(...), user: models.User = Depends(current_user)):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Upload a JPG, PNG or WEBP image.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image must be 5 MB or smaller.")
    if not data:
        raise HTTPException(400, "The uploaded image is empty.")
    try:
        return await asyncio.to_thread(_analyse_clothing_image, data, file.content_type)
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(502, "The AI returned an unreadable result. Please try again.")
    except Exception as exc:
        print(f"Clothing analysis failed: {type(exc).__name__}: {exc}")
        message = str(exc)
        if "Cannot reach Ollama" in message or "not configured" in message or "AI_PROVIDER" in message:
            raise HTTPException(503, message)
        raise HTTPException(502, "Could not analyse this image right now. Please retry or enter details manually.")

@app.post("/api/ai/extract-outfit", response_model=schemas.OutfitExtraction)
async def extract_outfit(file: UploadFile = File(...), user: models.User = Depends(current_user)):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Upload a JPG, PNG or WEBP image.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded image is empty.")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image must be 10 MB or smaller.")
    try:
        crops = await asyncio.to_thread(_extract_garment_crops, data)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        print(f"Garment extraction failed: {type(exc).__name__}: {exc}")
        raise HTTPException(502, "Could not extract clothing from this image. Try a clear, full-body photo.")
    if not crops:
        raise HTTPException(422, "No clothing was detected. Try a clear photo of a person wearing an outfit.")
    garments = []
    for category, subcategory, crop in crops:
        filename = f"user-{user.id}-garment-{uuid4().hex}.png"
        (UPLOAD_DIR / filename).write_bytes(crop)
        analysis = {"name": subcategory, "category": category, "subcategory": subcategory, "confidence": 0.8}
        try:
            details = await asyncio.to_thread(_analyse_clothing_image, crop, "image/png")
            details["category"] = category
            details["subcategory"] = details.get("subcategory") or subcategory
            analysis = details
        except Exception:
            pass
        garments.append({"image_url": f"/uploads/{filename}", "analysis": analysis})
    return {"garments": garments}

def _normalise(value):
    return (value or "").strip().lower()

def _colour_score(a, b):
    a, b = _normalise(a), _normalise(b)
    if not a or not b:
        return 0.5
    neutrals = {"black", "white", "cream", "beige", "ivory", "grey", "gray", "navy", "brown", "tan", "denim"}
    if a == b:
        return 0.65
    if a in neutrals or b in neutrals:
        return 0.95
    pairs = [
        ({"blue", "orange"}, 0.9), ({"green", "pink"}, 0.9),
        ({"purple", "yellow"}, 0.9), ({"red", "green"}, 0.45),
        ({"blue", "green"}, 0.75), ({"brown", "blue"}, 0.9),
    ]
    for pair, score in pairs:
        if any(c in a for c in pair) and any(c in b for c in pair):
            return score
    return 0.7

def _recommend_outfits(items, wear_logs, occasion, weather, limit):
    from itertools import product
    groups = {
        "top": [i for i in items if i.category == "Tops"],
        "bottom": [i for i in items if i.category == "Bottoms"],
        "shoe": [i for i in items if i.category == "Footwear"],
        "outer": [i for i in items if i.category == "Outerwear"],
        "accessory": [i for i in items if i.category == "Accessories"],
    }
    if not groups["top"] or not groups["bottom"]:
        return {"recommendations": [], "message": "Add at least one top and one bottom to generate complete outfit suggestions."}
    recent_sets = set()
    for log in wear_logs:
        if log.outfit:
            recent_sets.add(frozenset(item.id for item in log.outfit.items))
    candidates = []
    # Keep the search bounded for large wardrobes; optional layers/accessories are added as variations.
    tops = groups["top"][:20]
    bottoms = groups["bottom"][:20]
    shoes = groups["shoe"][:12] or [None]
    outers = groups["outer"][:8] or [None]
    accessories = groups["accessory"][:8] or [None]
    for top, bottom in product(tops, bottoms):
        for shoe in shoes:
            base = [top, bottom] + ([shoe] if shoe else [])
            for outer in outers[:3]:
                for accessory in accessories[:3]:
                    chosen = base + ([outer] if outer else []) + ([accessory] if accessory else [])
                    ids = frozenset(i.id for i in chosen)
                    if len(ids) < 2:
                        continue
                    colour = _colour_score(top.colour, bottom.colour)
                    if shoe:
                        colour = (colour + _colour_score(shoe.colour, top.colour)) / 2
                    styles = {_normalise(i.style) for i in chosen if i.style}
                    style_score = 1.0 if len(styles) <= 1 else max(0.55, 1 - 0.12 * (len(styles)-1))
                    occ = _normalise(occasion)
                    occ_score = 1.0 if not occ or any(occ in _normalise(i.occasion) or occ in _normalise(i.style) for i in chosen) else 0.78
                    repeat_penalty = 0.25 if ids in recent_sets else 0
                    weather_score = 0.75
                    wx = _normalise(weather)
                    has_outer = outer is not None
                    if wx == "cold":
                        weather_score = 1.0 if has_outer else 0.65
                    elif wx == "hot":
                        weather_score = 0.95 if not has_outer else 0.60
                    elif wx == "rainy":
                        weather_score = 0.85 if shoe else 0.65
                    score = max(0.35, min(0.99, 0.48*colour + 0.22*style_score + 0.18*occ_score + 0.12*weather_score - repeat_penalty))
                    reasons = []
                    if colour >= 0.85: reasons.append("The colours work well together")
                    elif colour >= 0.65: reasons.append("A balanced colour combination")
                    if len(styles) <= 1: reasons.append("A consistent overall style")
                    if shoe: reasons.append("Includes footwear from your wardrobe")
                    if ids in recent_sets: reasons.append("Previously worn combination — try swapping a piece")
                    if wx == "cold":
                        reasons.append("Cold-weather preference: " + ("includes an outer layer" if has_outer else "consider adding an outer layer"))
                    elif wx == "hot" and not has_outer:
                        reasons.append("Hot-weather preference: keeps the look light")
                    elif wx == "rainy" and shoe:
                        reasons.append("Rainy-day preference: includes your footwear (check whether it is weather-appropriate)")
                    candidates.append({"items": chosen, "item_ids": list(ids), "score": round(score, 2), "reasons": reasons, "recently_worn": ids in recent_sets})
    # Prefer fresh combinations and rank by transparent heuristic score.
    candidates.sort(key=lambda c: (c["recently_worn"], -c["score"], len(c["items"])))
    results, seen = [], set()
    for candidate in candidates:
        key = frozenset(candidate["item_ids"])
        if key in seen: continue
        seen.add(key)
        results.append({
            "items": [{"id": i.id, "name": i.name, "category": i.category, "colour": i.colour, "image_url": i.image_url} for i in candidate["items"]],
            "item_ids": candidate["item_ids"], "score": candidate["score"],
            "reasons": candidate["reasons"], "recently_worn": candidate["recently_worn"]
        })
        if len(results) >= limit: break
    return {"recommendations": results, "message": None if results else "No fresh combinations found. Add more wardrobe variety or try a different occasion."}

@app.get("/api/outfits/recommendations")
def outfit_recommendations(occasion: str | None = None, weather: str | None = None, limit: int = 6, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    limit = max(1, min(limit, 12))
    items = db.scalars(select(models.ClothingItem).where(models.ClothingItem.owner_id == user.id).order_by(models.ClothingItem.created_at.desc())).all()
    wears = db.scalars(select(models.WearLog).where(models.WearLog.owner_id == user.id).options(selectinload(models.WearLog.outfit).selectinload(models.Outfit.items)).order_by(models.WearLog.worn_on.desc()).limit(30)).all()
    if weather and weather.lower() not in {"hot", "cold", "rainy", "mild"}:
        raise HTTPException(400, "Weather must be hot, cold, rainy or mild.")
    return _recommend_outfits(items, wears, occasion, weather, limit)

@app.get("/api/items", response_model=list[schemas.ItemOut])
def list_items(category: str | None = None, q: str | None = None, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    stmt = select(models.ClothingItem).where(models.ClothingItem.owner_id == user.id).order_by(models.ClothingItem.created_at.desc())
    if category and category.lower() != "all": stmt = stmt.where(models.ClothingItem.category.ilike(category))
    if q:
        term = f"%{q}%"
        stmt = stmt.where(models.ClothingItem.name.ilike(term) | models.ClothingItem.brand.ilike(term) | models.ClothingItem.colour.ilike(term))
    return db.scalars(stmt).all()

@app.post("/api/items", response_model=schemas.ItemOut, status_code=201)
def create_item(payload: schemas.ItemCreate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    item = models.ClothingItem(**payload.model_dump(), owner_id=user.id)
    db.add(item); db.commit(); db.refresh(item); return item

@app.get("/api/items/{item_id}", response_model=schemas.ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    return owned_item(db, item_id, user.id)

@app.patch("/api/items/{item_id}", response_model=schemas.ItemOut)
def update_item(item_id: int, payload: schemas.ItemUpdate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    item = owned_item(db, item_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(item, key, value)
    db.commit(); db.refresh(item); return item

@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    item = owned_item(db, item_id, user.id); db.delete(item); db.commit()

@app.get("/api/outfits", response_model=list[schemas.OutfitOut])
def list_outfits(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    stmt = select(models.Outfit).where(models.Outfit.owner_id == user.id).options(selectinload(models.Outfit.items)).order_by(models.Outfit.created_at.desc())
    return db.scalars(stmt).all()

@app.post("/api/outfits", response_model=schemas.OutfitOut, status_code=201)
def create_outfit(payload: schemas.OutfitCreate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    ids = list(dict.fromkeys(payload.item_ids))
    items = db.scalars(select(models.ClothingItem).where(models.ClothingItem.owner_id == user.id, models.ClothingItem.id.in_(ids))).all()
    if len(items) != len(ids): raise HTTPException(400, "One or more wardrobe items do not exist in your closet.")
    outfit = models.Outfit(name=payload.name, items=items, owner_id=user.id)
    db.add(outfit); db.commit(); db.refresh(outfit)
    return db.scalar(select(models.Outfit).options(selectinload(models.Outfit.items)).where(models.Outfit.id == outfit.id))

@app.patch("/api/outfits/{outfit_id}", response_model=schemas.OutfitOut)
def update_outfit(outfit_id: int, payload: schemas.OutfitUpdate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    outfit = db.scalar(select(models.Outfit).where(models.Outfit.id == outfit_id, models.Outfit.owner_id == user.id).options(selectinload(models.Outfit.items)))
    if not outfit:
        raise HTTPException(404, "Outfit not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(outfit, key, value)
    db.commit(); db.refresh(outfit)
    return db.scalar(select(models.Outfit).options(selectinload(models.Outfit.items)).where(models.Outfit.id == outfit.id))

@app.delete("/api/outfits/{outfit_id}", status_code=204)
def delete_outfit(outfit_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    outfit = db.scalar(select(models.Outfit).where(models.Outfit.id == outfit_id, models.Outfit.owner_id == user.id))
    if not outfit: raise HTTPException(404, "Outfit not found.")
    db.delete(outfit); db.commit()

@app.get("/api/wears", response_model=list[schemas.WearOut])
def list_wears(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    stmt = select(models.WearLog).where(models.WearLog.owner_id == user.id).options(selectinload(models.WearLog.outfit).selectinload(models.Outfit.items)).order_by(models.WearLog.worn_on.desc())
    return db.scalars(stmt).all()

@app.post("/api/wears", response_model=schemas.WearOut, status_code=201)
def create_wear(payload: schemas.WearCreate, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    if payload.outfit_id is not None:
        outfit = db.scalar(select(models.Outfit).where(models.Outfit.id == payload.outfit_id, models.Outfit.owner_id == user.id))
        if not outfit: raise HTTPException(400, "Saved outfit does not exist in your closet.")
    wear = models.WearLog(**payload.model_dump(), owner_id=user.id)
    db.add(wear); db.commit(); db.refresh(wear)
    return db.scalar(select(models.WearLog).options(selectinload(models.WearLog.outfit).selectinload(models.Outfit.items)).where(models.WearLog.id == wear.id))

@app.get("/api/analytics")
def analytics(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    items = db.scalars(select(models.ClothingItem).where(models.ClothingItem.owner_id == user.id)).all()
    outfits = db.scalars(select(models.Outfit).where(models.Outfit.owner_id == user.id).options(selectinload(models.Outfit.items))).all()
    wears = db.scalars(select(models.WearLog).where(models.WearLog.owner_id == user.id).options(selectinload(models.WearLog.outfit).selectinload(models.Outfit.items))).all()
    counts = {}
    outfit_counts = {}
    for wear in wears:
        if wear.outfit:
            outfit_counts[wear.outfit_id] = outfit_counts.get(wear.outfit_id, 0) + 1
            for item in wear.outfit.items:
                counts[item.id] = counts.get(item.id, 0) + 1
    item_stats = []
    for item in items:
        count = counts.get(item.id, 0)
        cost_per_wear = round(float(item.purchase_price) / count, 2) if item.purchase_price is not None and count else None
        item_stats.append({
            "item_id": item.id, "name": item.name, "category": item.category,
            "wear_count": count, "purchase_price": item.purchase_price,
            "cost_per_wear": cost_per_wear, "is_favorite": item.is_favorite,
            "image_url": item.image_url
        })
    repeated = sorted(
        [{"outfit_id": o.id, "name": o.name, "wear_count": outfit_counts.get(o.id, 0),
          "is_favorite": o.is_favorite, "item_ids": [i.id for i in o.items]}
         for o in outfits if outfit_counts.get(o.id, 0) > 1],
        key=lambda x: x["wear_count"], reverse=True
    )
    top = sorted([x for x in item_stats if x["wear_count"] > 0], key=lambda x: x["wear_count"], reverse=True)[:8]
    least = sorted(item_stats, key=lambda x: (x["wear_count"], x["name"].lower()))[:8]
    priced = [x for x in item_stats if x["cost_per_wear"] is not None]
    return {
        "item_count": len(items), "outfit_count": len(outfits), "wear_count": len(wears),
        "unworn_count": sum(1 for x in item_stats if x["wear_count"] == 0),
        "favorite_item_count": sum(1 for x in items if x.is_favorite),
        "favorite_outfit_count": sum(1 for o in outfits if o.is_favorite),
        "most_worn": top, "least_worn": least, "item_stats": item_stats,
        "repeated_outfits": repeated[:6],
        "average_cost_per_wear": round(sum(x["cost_per_wear"] for x in priced) / len(priced), 2) if priced else None
    }

@app.get("/api/outfits/{outfit_id}/repeat-check")
def outfit_repeat_check(outfit_id: int, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    outfit = db.scalar(select(models.Outfit).where(models.Outfit.id == outfit_id, models.Outfit.owner_id == user.id))
    if not outfit:
        raise HTTPException(404, "Outfit not found.")
    logs = db.scalars(select(models.WearLog).where(
        models.WearLog.owner_id == user.id, models.WearLog.outfit_id == outfit_id
    ).order_by(models.WearLog.worn_on.desc())).all()
    last_worn = logs[0].worn_on.isoformat() if logs else None
    days_since = (date.today() - logs[0].worn_on).days if logs else None
    return {"outfit_id": outfit_id, "wear_count": len(logs), "last_worn": last_worn,
            "days_since_last_wear": days_since,
            "repeat_warning": bool(days_since is not None and days_since < 7)}
