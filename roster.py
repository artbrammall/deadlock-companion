import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "companion.db"


def available_heroes():
    return {
        path.stem
        for path in (ROOT / "portraits").glob("*.png")
    }


def connect():
    DATABASE.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS roster (
            hero TEXT PRIMARY KEY
        )
    """)
    connection.commit()
    return connection


def get_roster():
    connection = connect()
    try:
        rows = connection.execute(
            "SELECT hero FROM roster ORDER BY hero"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()


def change_roster(action, heroes):
    invalid = sorted(set(heroes) - available_heroes())
    if invalid:
        raise ValueError(f"Unknown hero names: {', '.join(invalid)}")

    connection = connect()
    try:
        with connection:
            if action == "add":
                connection.executemany(
                    "INSERT OR IGNORE INTO roster (hero) VALUES (?)",
                    [(hero,) for hero in heroes],
                )
            else:
                connection.executemany(
                    "DELETE FROM roster WHERE hero = ?",
                    [(hero,) for hero in heroes],
                )
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "add", "remove"])
    parser.add_argument("heroes", nargs="*")
    args = parser.parse_args()

    if args.action == "list":
        if args.heroes:
            parser.error("'list' does not accept hero names")
    else:
        if not args.heroes:
            parser.error("Provide at least one hero name")
        try:
            change_roster(args.action, args.heroes)
        except ValueError as error:
            parser.error(str(error))

    heroes = get_roster()
    print("Saved roster: " + (", ".join(heroes) if heroes else "(empty)"))


if __name__ == "__main__":
    main()