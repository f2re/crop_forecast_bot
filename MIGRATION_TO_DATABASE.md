# Migration to PostgreSQL Database

## Overview

This document describes the migration from JSON file-based storage to PostgreSQL database storage for the Crop Forecast Bot.

## What Changed

### 1. Storage Backend
- **Before**: User coordinates were stored in `data/coordinates.json` file
- **After**: User data and coordinates are stored in PostgreSQL database

### 2. Database Schema

A new `users` table has been created with the following structure:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    latitude FLOAT,
    longitude FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 3. New Files

- `src/database/__init__.py` - Database connection and initialization
- `src/database/models.py` - SQLAlchemy models
- `src/database/crud.py` - Database operations (CRUD)

### 4. Modified Files

- `src/storage/coordinates.py` - Now uses database instead of JSON
- `config/settings.py` - Added database configuration
- `run_bot.py` - Added database initialization on startup
- `docker-compose.yml` - Added PostgreSQL service
- `requirements.txt` - Added `asyncpg` for async PostgreSQL support
- `.env.example` - Added database configuration variables
- `.env.docker.example` - Added database configuration variables

## Benefits

1. **No File Permission Issues**: Eliminated permission errors when writing to JSON files in Docker
2. **Better Performance**: Database operations are faster and more efficient
3. **Scalability**: Can handle many more users without file system limitations
4. **Data Integrity**: ACID compliance ensures data consistency
5. **Concurrent Access**: Multiple bot instances can share the same database
6. **Additional Features**: Easy to add user tracking, analytics, and more features

## Migration Steps

### For Docker Deployment

1. Pull the latest changes:
   ```bash
   git pull
   ```

2. Update your `.env` file with database credentials (if not using defaults):
   ```bash
   DB_NAME=crop_forecast_bot
   DB_USER=postgres
   DB_PASSWORD=your_secure_password
   ```

3. Rebuild and restart containers:
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

4. The database will be automatically initialized on first startup.

### For Local Development

1. Install PostgreSQL if not already installed:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql postgresql-contrib

   # macOS
   brew install postgresql
   ```

2. Create database:
   ```sql
   CREATE DATABASE crop_forecast_bot;
   CREATE USER postgres WITH PASSWORD 'postgres';
   GRANT ALL PRIVILEGES ON DATABASE crop_forecast_bot TO postgres;
   ```

3. Update your `.env` file with database connection details.

4. Install updated dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Run the bot:
   ```bash
   python run_bot.py
   ```

   The database tables will be created automatically on first run.

## Data Migration from JSON

If you have existing user data in `data/coordinates.json`, you can migrate it using this script:

```python
import json
import asyncio
from config.settings import get_database_url
from src.database import init_db
from src.database.crud import save_coordinates

async def migrate_json_to_db():
    """Migrate coordinates from JSON file to database"""

    # Initialize database
    db_url = get_database_url()
    db = init_db(db_url)
    await db.create_tables()

    # Read JSON file
    try:
        with open('data/coordinates.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No coordinates.json file found, nothing to migrate")
        return

    # Migrate each user
    migrated = 0
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
                print(f"Migrated user {user_id}")
            except Exception as e:
                print(f"Error migrating user {user_id}: {e}")

    print(f"Migration complete! Migrated {migrated} users")

if __name__ == "__main__":
    asyncio.run(migrate_json_to_db())
```

Save this as `scripts/migrate_json_to_db.py` and run it:

```bash
python scripts/migrate_json_to_db.py
```

## Environment Variables

### Required

- `DATABASE_URL` - Full PostgreSQL connection URL, OR:
- `DB_HOST` - Database host (default: `postgres` in Docker, `localhost` otherwise)
- `DB_PORT` - Database port (default: `5432`)
- `DB_NAME` - Database name (default: `crop_forecast_bot`)
- `DB_USER` - Database user (default: `postgres`)
- `DB_PASSWORD` - Database password

### Example

```bash
# Option 1: Use DATABASE_URL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/crop_forecast_bot

# Option 2: Use individual variables
DB_HOST=localhost
DB_PORT=5432
DB_NAME=crop_forecast_bot
DB_USER=postgres
DB_PASSWORD=postgres
```

## Troubleshooting

### Database Connection Errors

If you see errors like "could not connect to server":

1. Check that PostgreSQL is running:
   ```bash
   docker-compose ps  # for Docker
   sudo systemctl status postgresql  # for local
   ```

2. Verify credentials in `.env` file
3. Check PostgreSQL logs:
   ```bash
   docker-compose logs postgres
   ```

### Permission Errors

The migration eliminates file permission errors. If you still see them:

1. Ensure database is properly initialized
2. Check database user has proper permissions
3. Review application logs for specific errors

## Rollback

If you need to rollback to JSON storage:

1. Checkout the previous commit:
   ```bash
   git checkout <previous-commit-hash>
   ```

2. Rebuild containers:
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

Note: You will lose any data stored in the database after migration.

## Support

For issues or questions, please create an issue on GitHub or contact the development team.
