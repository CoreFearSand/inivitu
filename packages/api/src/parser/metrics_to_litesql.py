import sqlite3
from pathlib import Path
from typing import Union, Dict, Any


def populate_countries(
    data: Dict[str, Any],
    db_file: Union[str, Path],
    playthrough_id: str
) -> None:
    """From the melted JSON `data`, extract and store current metrics per country:
      - total GDP
      - total population
      - weekly income
      - weekly expenses
      - government cash reserves (money)
      - prestige
      - literacy
      - state of learning (sol)
      - infamy
    Stored in a table `country_snapshot` keyed by playthrough and date.

    Args:
        data (Dict[str, Any]): The melted JSON data containing country metrics.
        db_file (Union[str, Path]): The path to the SQLite database file.
        playthrough_id (str): The ID of the playthrough.
        
    Returns:
        None: This function does not return any value. It commits the data to the database.
        
    Raises:
        sqlite3.Error: If there is an error with the SQLite database operations.
    """
    db_path = Path(db_file)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # ensure table exists
    cur.executescript("""
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS country_snapshot (
        playthrough_id TEXT,
        save_date TEXT,
        country_id TEXT,
        gdp REAL,
        population REAL,
        weekly_income REAL,
        weekly_expenses REAL,
        money REAL,
        prestige REAL,
        literacy REAL,
        sol REAL,
        infamy REAL,
        PRIMARY KEY (playthrough_id, save_date, country_id)
    );
    """
    )


    save_date = data.get("meta", {}).get("date") or data.get("game_date") or ""

    countries = data.get("country_manager", {}).get("database", {})
    for cid, info in countries.items():
        gdp = float(info.get("gdp", 0))
        population = float(info.get("population", 0))
        budget = info.get("budget", {})
        weekly_inc = 0.0
        weekly_exp = 0.0
        if budget:
            weekly_inc = float(budget.get("weekly_income", [0])[0]) if isinstance(budget.get("weekly_income"), list) else 0.0
            weekly_exp = float(budget.get("weekly_expenses", [0])[0]) if isinstance(budget.get("weekly_expenses"), list) else 0.0
        money = float(budget.get("money", info.get("money", 0)))
        prestige = float(info.get("prestige", 0))
        literacy = float(info.get("literacy", 0))
        sol = float(info.get("sol", 0))
        infamy = float(info.get("infamy", 0))

        cur.execute(
            "INSERT OR REPLACE INTO country_snapshot"
            " (playthrough_id, save_date, country_id, gdp, population, weekly_income, weekly_expenses, money, prestige, literacy, sol, infamy)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (playthrough_id, save_date, cid, gdp, population, weekly_inc, weekly_exp, money, prestige, literacy, sol, infamy)
        )

    conn.commit()
    conn.close()
    