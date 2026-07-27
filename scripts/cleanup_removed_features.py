"""Remove retired rent-payment and luxury data from a SQLite database."""
import argparse
import sqlite3
from pathlib import Path


RETIRED_TABLES = [
    "luxury_product_orders",
    "luxury_products",
    "rent_payments",
    "landlord_sales_assignments",
    "tenants",
    "landlord_profiles",
]


def cleanup(database_path: Path) -> list[str]:
    resolved = database_path.resolve(strict=True)
    connection = sqlite3.connect(resolved)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        with connection:
            for table in RETIRED_TABLES:
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute(
                "DELETE FROM merchant_pg_configs WHERE provider_id IN "
                "(SELECT id FROM pg_providers WHERE code = ?)",
                ("ongi",),
            )
            connection.execute("DELETE FROM pg_providers WHERE code = ?", ("ongi",))
            connection.execute(
                "DELETE FROM users WHERE role IN (?, ?)",
                ("LANDLORD", "landlord"),
            )
            terminal_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(terminal_devices)")
            }
            if "api_key_plain" in terminal_columns:
                connection.execute("UPDATE terminal_devices SET api_key_plain = NULL")
                connection.execute("ALTER TABLE terminal_devices DROP COLUMN api_key_plain")

        return [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
            if any(keyword in row[0].lower() for keyword in ("landlord", "tenant", "rent", "luxury"))
        ]
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    remaining = cleanup(args.database)
    print(f"Remaining retired tables: {remaining}")
