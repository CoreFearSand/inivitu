from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from pathlib import Path
from typing import Optional, Any

from .config import VICTORIA3_SAVES_PATH, GAME_DATA_DB_PATH, CONFIG_DB_PATH
from .db import (
    fetch_saves, fetch_countries, fetch_wars,
    fetch_war_participants, fetch_battles, fetch_country_metrics
)
from .parser.v3_to_json import v3_to_json
from .parser.metrics_to_litesql import (
    create_schema, save_metadata, save_countries, save_country_metrics
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Settings endpoints ---
class Settings(BaseModel):
    vic3_saves_path: str
    game_data_db_path: str

@app.get("/api/settings", response_model=Settings)
def get_settings():
    """Return current application settings."""
    return Settings(
        vic3_saves_path=str(VICTORIA3_SAVES_PATH),
        game_data_db_path=str(GAME_DATA_DB_PATH)
    )

@app.post("/api/settings")
def update_settings(settings: Settings):
    """Persist new settings to the config database."""
    # ensure config DB and Settings table exist
    conn = sqlite3.connect(CONFIG_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS Settings (
            name TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    # upsert values
    for key, val in settings.model_dump().items():
        cur.execute(
            "INSERT INTO Settings (name, value) VALUES (?, ?)"
            " ON CONFLICT(name) DO UPDATE SET value=excluded.value;",
            (key, val)
        )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/api/saves")
def api_saves(limit: Optional[int] = None):
    """Fetch list of saves, optionally limited."""
    return fetch_saves(limit)

@app.get("/api/countries")
def api_countries(save_id: Optional[str] = None):
    """Fetch countries for a given save_id."""
    if save_id is None:
        raise HTTPException(status_code=400, detail="Missing save_id parameter")
    return fetch_countries(save_id)

@app.get("/api/wars")
def api_wars(save_id: Optional[str] = None, status: Optional[str] = None):
    """Fetch wars, optionally filtered."""
    return fetch_wars(save_id, status)

@app.get("/api/war_participants")
def api_war_participants(war_id: Optional[str] = None):
    """Fetch participants in a war."""
    if not war_id:
        raise HTTPException(status_code=400, detail="Missing war_id parameter")
    return fetch_war_participants(war_id)

@app.get("/api/battles")
def api_battles(war_id: Optional[str] = None, country_tag: Optional[str] = None):
    """Fetch battles, filter by war or country."""
    return fetch_battles(war_id, country_tag)

@app.get("/api/country_metrics")
def api_metrics(country_tag: Optional[str] = None, metric_name: Optional[str] = None, limit: Optional[int] = None):
    """Fetch metrics for a country."""
    if not country_tag:
        raise HTTPException(status_code=400, detail="Missing country_tag parameter")
    return fetch_country_metrics(country_tag, metric_name, limit)

# --- Save file upload & processing ---
@app.post("/api/upload_save")
def upload_and_process(
    file: UploadFile = File(...),
    use_rakaly_path: str = Form(None)
) -> dict[str, Any]:
    """Endpoint to upload a Victoria 3 save file, parse to JSON and ingest metrics."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in uploaded file")
    temp_path = Path(VICTORIA3_SAVES_PATH) / file.filename
    with open(temp_path, "wb") as f:
        f.write(file.file.read())
    data = v3_to_json(temp_path, use_rakaly_path)
    create_schema(GAME_DATA_DB_PATH)
    conn = sqlite3.connect(GAME_DATA_DB_PATH)
    save_metadata(conn, data)
    save_countries(conn, data)
    save_country_metrics(conn, data)
    conn.close()
    return {"status": "processed", "save_id": data.get("playthrough_id")}
