from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class AuthRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class AuthLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    subcategory: str | None = None
    colour: str | None = None
    secondary_colour: str | None = None
    pattern: str | None = None
    material: str | None = None
    occasion: str | None = None
    ai_confidence: float | None = Field(default=None, ge=0, le=1)
    purchase_price: float | None = Field(default=None, ge=0)
    is_favorite: bool = False
    brand: str | None = None
    style: str | None = None
    product_code: str | None = None
    image_url: str | None = None
    notes: str | None = None

class ItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    colour: str | None = None
    secondary_colour: str | None = None
    pattern: str | None = None
    material: str | None = None
    occasion: str | None = None
    ai_confidence: float | None = Field(default=None, ge=0, le=1)
    purchase_price: float | None = Field(default=None, ge=0)
    is_favorite: bool | None = None
    brand: str | None = None
    style: str | None = None
    product_code: str | None = None
    image_url: str | None = None
    notes: str | None = None

class ItemOut(ItemCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class OutfitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    item_ids: list[int] = Field(min_length=1, max_length=6)

class OutfitOut(BaseModel):
    id: int
    name: str
    is_favorite: bool = False
    created_at: datetime
    items: list[ItemOut]
    model_config = ConfigDict(from_attributes=True)

class OutfitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_favorite: bool | None = None

class WearCreate(BaseModel):
    worn_on: date
    outfit_id: int | None = None
    note: str | None = Field(default=None, max_length=240)

class WearOut(BaseModel):
    id: int
    worn_on: date
    outfit_id: int | None
    note: str | None
    outfit: OutfitOut | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ClothingAnalysis(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str
    subcategory: str | None = None
    colour: str | None = None
    secondary_colour: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: str | None = None
    occasion: str | None = None
    description: str | None = None
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

class ExtractedGarment(BaseModel):
    image_url: str
    analysis: ClothingAnalysis

class OutfitExtraction(BaseModel):
    garments: list[ExtractedGarment]
