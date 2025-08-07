import sqlite3
from pathlib import Path
import pandas as pd

db_path = Path(__file__).resolve().parent / "storage" / "game_data.db"