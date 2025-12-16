#!/usr/bin/env python3
"""
Migration script to transfer user coordinates from JSON file to PostgreSQL database.

Usage:
    python scripts/migrate_json_to_db.py
"""
import json
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import get_database_url
from src.database import init_db
from src.database.crud import save_coordinates


async def migrate_json_to_db():
    """Migrate coordinates from JSON file to database"""

    print("=" * 60)
    print("JSON to Database Migration Script")
    print("=" * 60)
    print()

    # Initialize database
    db_url = get_database_url()
    print(f"📊 Database URL: {db_url.split('@')[1] if '@' in db_url else db_url}")

    try:
        db = init_db(db_url)
        await db.create_tables()
        print("✓ Database initialized and tables created")
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        return

    # Read JSON file
    json_file = 'data/coordinates.json'
    print(f"\n📂 Reading JSON file: {json_file}")

    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        print(f"✓ Found {len(data)} users in JSON file")
    except FileNotFoundError:
        print("✗ No coordinates.json file found, nothing to migrate")
        return
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON format: {e}")
        return

    if not data:
        print("ℹ No data to migrate")
        return

    # Migrate each user
    print("\n🔄 Starting migration...")
    migrated = 0
    errors = 0

    async with db.get_session() as session:
        for user_id, coords in data.items():
            try:
                await save_coordinates(
                    session=session,
                    telegram_id=int(user_id),
                    latitude=coords['latitude'],
                    longitude=coords['longitude']
                )
                migrated += 1
                print(f"  ✓ Migrated user {user_id}: ({coords['latitude']}, {coords['longitude']})")
            except Exception as e:
                errors += 1
                print(f"  ✗ Error migrating user {user_id}: {e}")

    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total users in JSON: {len(data)}")
    print(f"Successfully migrated: {migrated}")
    print(f"Errors: {errors}")
    print()

    if migrated > 0:
        print("✓ Migration completed successfully!")
        print()
        print("Next steps:")
        print("1. Verify data in database")
        print("2. Backup the JSON file: cp data/coordinates.json data/coordinates.json.backup")
        print("3. Remove or archive the JSON file after verification")
    else:
        print("⚠ No users were migrated. Please check for errors above.")


if __name__ == "__main__":
    try:
        asyncio.run(migrate_json_to_db())
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user")
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
