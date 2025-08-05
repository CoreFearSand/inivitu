import sqlite3
from pathlib import Path
import pandas as pd

db_file = Path("C:\\Users\\kaare\\OneDrive\\Dokumenter\\inivitu\\packages\\api\\src\\storage\\game_data.db")
conn = sqlite3.connect(db_file)

# List tables
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
print(tables)

# Preview some data
df = pd.read_sql("SELECT * FROM country_snapshot LIMIT 20", conn)
print(df)

conn.close()