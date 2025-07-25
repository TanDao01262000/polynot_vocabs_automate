# Supabase Migration Guide

This guide will help you migrate your vocabulary learning application from SQLite to Supabase, a hosted PostgreSQL database with real-time capabilities.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Supabase Setup](#supabase-setup)
3. [Database Schema Migration](#database-schema-migration)
4. [Code Changes](#code-changes)
5. [Environment Configuration](#environment-configuration)
6. [Data Migration](#data-migration)
7. [Testing](#testing)
8. [Deployment Considerations](#deployment-considerations)

## Prerequisites

Before starting the migration, ensure you have:
- A Supabase account (sign up at [supabase.com](https://supabase.com))
- Your existing SQLite database (`vocab.db`)
- Python environment with your current dependencies

## Supabase Setup

### 1. Create a New Supabase Project

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Click "New Project"
3. Choose your organization
4. Fill in project details:
   - Name: `vocab-learning-app` (or your preferred name)
   - Database Password: Generate a strong password
   - Region: Choose closest to your users
5. Click "Create new project"
6. Wait for the project to be ready (usually 2-3 minutes)

### 2. Get Connection Details

Once your project is ready:
1. Go to Settings → Database
2. Note down these connection details:
   - **Host**: `db.xxx.supabase.co`
   - **Database name**: `postgres`
   - **Port**: `5432`
   - **User**: `postgres`
   - **Password**: The password you set during project creation

### 3. Get API Keys

1. Go to Settings → API
2. Note down:
   - **Project URL**: `https://xxx.supabase.co`
   - **Anon public key**: `eyJ...` (for client-side access)
   - **Service role key**: `eyJ...` (for server-side access with full permissions)

## Database Schema Migration

### 1. Create Tables in Supabase

Go to the SQL Editor in your Supabase dashboard and run these SQL commands:

```sql
-- Enable UUID extension (recommended for PostgreSQL)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create vocab_entries table
CREATE TABLE vocab_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    translation TEXT NOT NULL,
    example TEXT NOT NULL,
    example_translation TEXT NOT NULL,
    level TEXT NOT NULL,
    part_of_speech TEXT,
    topic TEXT,
    target_language TEXT,
    original_language TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(word, topic, level, part_of_speech)
);

-- Create topic_lists table
CREATE TABLE topic_lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_name TEXT NOT NULL,
    topics JSONB NOT NULL,  -- Using JSONB for better performance
    category TEXT,
    level TEXT NOT NULL,
    target_language TEXT,
    original_language TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_vocab_entries_topic ON vocab_entries(topic);
CREATE INDEX idx_vocab_entries_level ON vocab_entries(level);
CREATE INDEX idx_vocab_entries_word ON vocab_entries(word);
CREATE INDEX idx_vocab_entries_created_at ON vocab_entries(created_at);
CREATE INDEX idx_topic_lists_level ON topic_lists(level);
CREATE INDEX idx_topic_lists_created_at ON topic_lists(created_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_vocab_entries_updated_at 
    BEFORE UPDATE ON vocab_entries 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_topic_lists_updated_at 
    BEFORE UPDATE ON topic_lists 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### 2. Set Up Row Level Security (RLS)

```sql
-- Enable RLS on tables
ALTER TABLE vocab_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_lists ENABLE ROW LEVEL SECURITY;

-- Create policies (adjust based on your authentication needs)
-- For now, allow all operations (you can restrict later)
CREATE POLICY "Allow all operations on vocab_entries" ON vocab_entries
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations on topic_lists" ON topic_lists
    FOR ALL USING (true) WITH CHECK (true);
```

## Code Changes

### 1. Update Requirements

Add these packages to your `requirements.txt`:

```txt
# Add these lines to your existing requirements.txt
supabase==2.4.0
psycopg2-binary==2.9.9
asyncpg==0.29.0
```

### 2. Create New Database Class

Create a new file `supabase_database.py`:

```python
import os
import json
from typing import List, Optional
from datetime import datetime
from supabase import create_client, Client
from models import VocabEntry, CEFRLevel
import asyncio
import asyncpg

class SupabaseVocabDatabase:
    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Direct PostgreSQL connection for advanced operations
        self.db_url = os.getenv("SUPABASE_DB_URL")
    
    def insert_vocab_entries(self, entries: List[VocabEntry], topic: str = None, 
                           target_language: str = None, original_language: str = None):
        """Insert multiple vocab entries into the database, skipping duplicates"""
        inserted_count = 0
        skipped_count = 0
        
        for entry in entries:
            try:
                data = {
                    "word": entry.word,
                    "definition": entry.definition,
                    "translation": entry.translation,
                    "example": entry.example,
                    "example_translation": entry.example_translation,
                    "level": entry.level.value,
                    "part_of_speech": getattr(entry, 'part_of_speech', None),
                    "topic": topic,
                    "target_language": target_language,
                    "original_language": original_language
                }
                
                # Use upsert to handle duplicates
                result = self.supabase.table("vocab_entries").upsert(
                    data,
                    on_conflict="word,topic,level,part_of_speech"
                ).execute()
                
                if result.data:
                    inserted_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                print(f"Error inserting {entry.word}: {str(e)}")
                skipped_count += 1
        
        print(f"Inserted {inserted_count} new vocab entries, skipped {skipped_count} duplicates")
    
    def get_vocab_entries(self, topic: str = None, level: CEFRLevel = None, limit: int = 100) -> List[VocabEntry]:
        """Retrieve vocab entries from database with optional filters"""
        query = self.supabase.table("vocab_entries").select("*")
        
        if topic:
            query = query.eq("topic", topic)
        
        if level:
            query = query.eq("level", level.value)
        
        query = query.order("created_at", desc=True).limit(limit)
        
        result = query.execute()
        
        entries = []
        for row in result.data:
            entry = VocabEntry(
                word=row["word"],
                definition=row["definition"],
                translation=row["translation"],
                example=row["example"],
                example_translation=row["example_translation"],
                level=CEFRLevel(row["level"])
            )
            entries.append(entry)
        
        return entries
    
    def get_existing_combinations(self, topic: str = None) -> List[tuple]:
        """Get existing word combinations to avoid duplicates"""
        query = self.supabase.table("vocab_entries").select("word,level,part_of_speech")
        
        if topic:
            query = query.eq("topic", topic)
        
        result = query.execute()
        
        return [(row["word"], row["level"], row["part_of_speech"]) for row in result.data]
    
    def save_topic_list(self, topics: List[str], list_name: str = None, 
                       category: str = None, level: CEFRLevel = CEFRLevel.A2,
                       target_language: str = "Vietnamese", original_language: str = "English"):
        """Save a custom topic list to the database"""
        if not list_name:
            list_name = f"custom_list_{len(topics)}_topics"
        
        data = {
            "list_name": list_name,
            "topics": topics,  # Supabase handles JSON automatically
            "category": category,
            "level": level.value,
            "target_language": target_language,
            "original_language": original_language
        }
        
        result = self.supabase.table("topic_lists").insert(data).execute()
        
        if result.data:
            print(f"Saved topic list '{list_name}' with {len(topics)} topics")
        else:
            print(f"Failed to save topic list '{list_name}'")
    
    def get_topic_lists(self) -> List[dict]:
        """Get all saved topic lists"""
        result = self.supabase.table("topic_lists").select("*").order("created_at", desc=True).execute()
        
        topic_lists = []
        for row in result.data:
            topic_lists.append({
                "list_name": row["list_name"],
                "topics": row["topics"],  # Already parsed as JSON
                "category": row["category"],
                "level": row["level"],
                "target_language": row["target_language"],
                "original_language": row["original_language"],
                "created_at": row["created_at"]
            })
        
        return topic_lists
    
    def get_stats(self) -> dict:
        """Get database statistics"""
        # Count total vocab entries
        vocab_count = self.supabase.table("vocab_entries").select("id", count="exact").execute()
        
        # Count by level
        level_stats = {}
        for level in CEFRLevel:
            count = self.supabase.table("vocab_entries").select("id", count="exact").eq("level", level.value).execute()
            level_stats[level.value] = count.count
        
        # Count topic lists
        topic_lists_count = self.supabase.table("topic_lists").select("id", count="exact").execute()
        
        return {
            "total_vocab_entries": vocab_count.count,
            "level_distribution": level_stats,
            "total_topic_lists": topic_lists_count.count
        }
```

### 3. Update Your Main Application

Update `vocab_agent.py` to use the new database:

```python
# Replace the database import and initialization
# from database import VocabDatabase
from supabase_database import SupabaseVocabDatabase

# Replace this line:
# db = VocabDatabase()
# With:
db = SupabaseVocabDatabase()
```

## Environment Configuration

### 1. Update Your `.env` File

Add these environment variables to your `.env` file:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql://postgres:your-password@db.your-project-id.supabase.co:5432/postgres

# Keep your existing environment variables
OPENAI_API_KEY=your-openai-key
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=polynot
```

### 2. Update `.gitignore`

Make sure your `.gitignore` includes:

```gitignore
.env
*.db
__pycache__/
*.pyc
.vscode/
.idea/
```

## Data Migration

### 1. Export Data from SQLite

Create a migration script `migrate_data.py`:

```python
import sqlite3
import json
from supabase_database import SupabaseVocabDatabase
from models import VocabEntry, CEFRLevel
from dotenv import load_dotenv

load_dotenv()

def migrate_sqlite_to_supabase():
    # Connect to SQLite
    sqlite_conn = sqlite3.connect("vocab.db")
    cursor = sqlite_conn.cursor()
    
    # Initialize Supabase
    supabase_db = SupabaseVocabDatabase()
    
    print("Starting migration...")
    
    # Migrate vocab_entries
    print("Migrating vocab entries...")
    cursor.execute("SELECT * FROM vocab_entries")
    vocab_rows = cursor.fetchall()
    
    for row in vocab_rows:
        try:
            entry = VocabEntry(
                word=row[1],
                definition=row[2],
                translation=row[3],
                example=row[4],
                example_translation=row[5],
                level=CEFRLevel(row[6])
            )
            
            supabase_db.insert_vocab_entries(
                [entry], 
                topic=row[8], 
                target_language=row[9], 
                original_language=row[10]
            )
        except Exception as e:
            print(f"Error migrating vocab entry {row[1]}: {e}")
    
    # Migrate topic_lists
    print("Migrating topic lists...")
    cursor.execute("SELECT * FROM topic_lists")
    topic_rows = cursor.fetchall()
    
    for row in topic_rows:
        try:
            topics = json.loads(row[2])  # Parse JSON topics
            supabase_db.save_topic_list(
                topics=topics,
                list_name=row[1],
                category=row[3],
                level=CEFRLevel(row[4]),
                target_language=row[5],
                original_language=row[6]
            )
        except Exception as e:
            print(f"Error migrating topic list {row[1]}: {e}")
    
    sqlite_conn.close()
    print("Migration completed!")

if __name__ == "__main__":
    migrate_sqlite_to_supabase()
```

### 2. Run the Migration

```bash
# Install new dependencies
pip install -r requirements.txt

# Run the migration script
python migrate_data.py
```

## Testing

### 1. Test Database Connection

Create a test script `test_supabase.py`:

```python
from supabase_database import SupabaseVocabDatabase
from models import VocabEntry, CEFRLevel
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    try:
        db = SupabaseVocabDatabase()
        
        # Test getting stats
        stats = db.get_stats()
        print("Database stats:", stats)
        
        # Test getting vocab entries
        entries = db.get_vocab_entries(limit=5)
        print(f"Retrieved {len(entries)} vocab entries")
        
        # Test getting topic lists
        topic_lists = db.get_topic_lists()
        print(f"Retrieved {len(topic_lists)} topic lists")
        
        print("✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_connection()
```

Run the test:

```bash
python test_supabase.py
```

### 2. Test Your Application

Run your main application and verify that all functionality works:

```bash
python vocab_agent.py
```

## Deployment Considerations

### 1. Production Environment Variables

For production, ensure you:
- Use environment variables instead of hardcoded values
- Use the service role key for server-side operations
- Keep the anon key for client-side operations (if applicable)
- Enable Row Level Security (RLS) with proper policies

### 2. Connection Pooling

For high-traffic applications, consider using connection pooling:

```python
# In your supabase_database.py, you can add connection pooling
import asyncpg
from asyncpg import Pool

class SupabaseVocabDatabase:
    def __init__(self):
        # ... existing code ...
        self.pool: Optional[Pool] = None
    
    async def get_pool(self) -> Pool:
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.db_url)
        return self.pool
```

### 3. Monitoring and Logging

Add proper logging and monitoring:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SupabaseVocabDatabase:
    def insert_vocab_entries(self, entries: List[VocabEntry], **kwargs):
        logger.info(f"Inserting {len(entries)} vocab entries")
        # ... existing code ...
        logger.info(f"Successfully inserted {inserted_count} entries")
```

## Cleanup

After successful migration and testing:

1. Backup your SQLite database:
   ```bash
   cp vocab.db vocab_backup.db
   ```

2. Remove SQLite-related code:
   - Delete or rename `database.py`
   - Remove SQLite imports from your codebase
   - Update any remaining references

3. Clean up migration files:
   ```bash
   rm migrate_data.py test_supabase.py
   ```

## Additional Features

With Supabase, you now have access to additional features:

### 1. Real-time Subscriptions

```python
# Listen to changes in vocab_entries table
def handle_vocab_changes(payload):
    print(f"Change detected: {payload}")

supabase.table("vocab_entries").on("INSERT", handle_vocab_changes).subscribe()
```

### 2. Built-in Authentication

```python
# Add user authentication
from supabase import create_client

supabase = create_client(url, key)

# Sign up
user = supabase.auth.sign_up({
    "email": "user@example.com",
    "password": "password123"
})

# Sign in
session = supabase.auth.sign_in_with_password({
    "email": "user@example.com", 
    "password": "password123"
})
```

### 3. File Storage

```python
# Upload files to Supabase Storage
bucket_name = "vocab-assets"
file_path = "audio/pronunciation.mp3"

with open("local_file.mp3", "rb") as f:
    supabase.storage.from_(bucket_name).upload(file_path, f)
```

## Troubleshooting

### Common Issues

1. **Connection Errors**: Verify your environment variables and network connectivity
2. **Permission Errors**: Check your RLS policies and API key permissions
3. **Data Type Errors**: Ensure your data types match the PostgreSQL schema
4. **Migration Failures**: Check for data inconsistencies in your SQLite database

### Getting Help

- [Supabase Documentation](https://supabase.com/docs)
- [Supabase Discord Community](https://discord.supabase.com)
- [GitHub Issues](https://github.com/supabase/supabase/issues)

---

**Congratulations!** You've successfully migrated from SQLite to Supabase. Your application now benefits from a hosted PostgreSQL database with real-time capabilities, built-in authentication, and scalable infrastructure.