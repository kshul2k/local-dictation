from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path.home() / "AppData" / "Roaming" / "open-whispr" / "transcriptions.db"


def main() -> None:
    uri = f"file:{DB_PATH}?mode=ro"
    print(f"db={DB_PATH}")
    with sqlite3.connect(uri, uri=True, timeout=2) as conn:
        tables = conn.execute(
            "select name, sql from sqlite_master where type='table' order by name"
        ).fetchall()
        for name, sql in tables:
            print(f"table={name}")
            print((sql or "").replace("\n", " "))
            columns = conn.execute(f"pragma table_info({name})").fetchall()
            print("columns=" + ", ".join(f"{col[1]}:{col[2]}" for col in columns))
            try:
                count = conn.execute(f"select count(*) from {name}").fetchone()[0]
                print(f"rows={count}")
            except sqlite3.DatabaseError as exc:
                print(f"rows_error={exc}")

        print("latest_transcriptions=")
        rows = conn.execute(
            """
            select id, length(text), length(raw_text), status, provider, model,
                   timestamp, created_at, audio_duration_ms
            from transcriptions
            order by id desc
            limit 8
            """
        ).fetchall()
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
