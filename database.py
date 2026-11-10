import sqlite3
import os

DB_PATH = "journal.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create main table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            timeframe TEXT,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            rr_ratio TEXT,
            status TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            image_path TEXT,
            trade_type TEXT
        )
    """)
    conn.commit()

    # Ensure backward compatibility by checking and adding missing columns dynamically
    cursor.execute("PRAGMA table_info(trades)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    migrations = [
        ("date_added", "ALTER TABLE trades ADD COLUMN date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("notes", "ALTER TABLE trades ADD COLUMN notes TEXT"),
        ("image_path", "ALTER TABLE trades ADD COLUMN image_path TEXT"),
        ("trade_type", "ALTER TABLE trades ADD COLUMN trade_type TEXT")
    ]

    for col_name, sql_stmt in migrations:
        if col_name not in existing_columns:
            try:
                cursor.execute(sql_stmt)
            except Exception as e:
                print(f"Migration error on {col_name}: {e}")

    conn.commit()
    conn.close()

def add_trade(payload):
    init_db()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (pair, timeframe, direction, entry_price, stop_loss, take_profit, rr_ratio, status, notes, image_path, trade_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.get("pair"),
            payload.get("timeframe"),
            payload.get("direction"),
            payload.get("entry_price"),
            payload.get("stop_loss"),
            payload.get("take_profit"),
            payload.get("rr_ratio"),
            payload.get("status"),
            payload.get("notes"),
            payload.get("image_path"),
            payload.get("trade_type")
        ))
        conn.commit()
        conn.close()
        return True, "Trade added successfully."
    except Exception as e:
        return False, str(e)

def fetch_all_trades():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, pair, timeframe, direction, entry_price, stop_loss, take_profit, rr_ratio, status, date_added, notes, image_path, trade_type FROM trades ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def fetch_trades_by_date(date_str):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, pair, timeframe, direction, entry_price, stop_loss, take_profit, rr_ratio, status, date_added, notes, image_path, trade_type FROM trades WHERE DATE(date_added) = DATE(?) ORDER BY id DESC", (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def fetch_daily_summary():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE(date_added) as trade_date, COUNT(*) as trade_count
        FROM trades
        GROUP BY DATE(date_added)
    """)
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: {"count": r[1]} for r in rows if r[0] is not None}

def update_trade(trade_id, payload):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE trades
        SET pair = ?, timeframe = ?, direction = ?, entry_price = ?, stop_loss = ?, take_profit = ?, status = ?, notes = ?, trade_type = ?
        WHERE id = ?
    """, (
        payload.get("pair"),
        payload.get("timeframe"),
        payload.get("direction"),
        payload.get("entry_price"),
        payload.get("stop_loss"),
        payload.get("take_profit"),
        payload.get("status"),
        payload.get("notes"),
        payload.get("trade_type"),
        trade_id
    ))
    conn.commit()
    conn.close()

def delete_trade(trade_id):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()
    conn.close()

def get_trade_image_path(trade_id):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None