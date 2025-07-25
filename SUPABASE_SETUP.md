# Supabase Migration Guide

This guide will help you migrate your vocabulary application from SQLite to Supabase.

## Step 1: Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up/log in
2. Click "New Project"
3. Choose your organization and enter project details:
   - **Name**: Your project name (e.g., "Vocab App")
   - **Database Password**: Choose a strong password
   - **Region**: Choose the closest region to your users
4. Click "Create new project"
5. Wait for the project to be set up (takes ~2 minutes)

## Step 2: Set Up Database Tables

1. In your Supabase dashboard, go to the **SQL Editor**
2. Create a new query and run the following SQL:

```sql
-- Create vocab_entries table
CREATE TABLE IF NOT EXISTS vocab_entries (
    id BIGSERIAL PRIMARY KEY,
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
    UNIQUE(word, topic, level, part_of_speech)
);

-- Create topic_lists table
CREATE TABLE IF NOT EXISTS topic_lists (
    id BIGSERIAL PRIMARY KEY,
    list_name TEXT NOT NULL,
    topics JSONB NOT NULL,
    category TEXT,
    level TEXT NOT NULL,
    target_language TEXT,
    original_language TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_vocab_entries_topic ON vocab_entries(topic);
CREATE INDEX IF NOT EXISTS idx_vocab_entries_level ON vocab_entries(level);
CREATE INDEX IF NOT EXISTS idx_vocab_entries_created_at ON vocab_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_topic_lists_created_at ON topic_lists(created_at);
```

3. Click **Run** to execute the SQL

## Step 3: Get Your Supabase Credentials

1. In your Supabase dashboard, go to **Settings** → **API**
2. Copy the following values:
   - **Project URL**
   - **Project API Keys** → **anon** **public** (for client-side access)

## Step 4: Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update your `.env` file with your Supabase credentials:
   ```env
   # Your existing OpenAI and LangSmith keys
   OPENAI_API_KEY=your_openai_api_key_here
   LANGSMITH_API_KEY=your_langsmith_api_key_here
   LANGSMITH_PROJECT=polynot

   # Add your Supabase credentials
   SUPABASE_URL=https://your-project-ref.supabase.co
   SUPABASE_ANON_KEY=your_supabase_anon_key_here
   ```

## Step 5: Install Dependencies

The Supabase dependencies should already be installed, but if not:

```bash
pip install supabase --break-system-packages
```

## Step 6: Test the Connection

Test that your Supabase connection works:

```python
python -c "
from database import VocabDatabase
try:
    db = VocabDatabase()
    print('✅ Supabase connection successful!')
except Exception as e:
    print(f'❌ Connection failed: {e}')
"
```

## Step 7: Migrate Your Data (Optional)

If you have existing data in your SQLite database, run the migration script:

```bash
python migrate_to_supabase.py
```

This will:
- Check your Supabase connection
- Transfer all `vocab_entries` from SQLite to Supabase
- Transfer all `topic_lists` from SQLite to Supabase
- Show you a summary of the migration

## Step 8: Test Your Application

1. Try running your existing vocabulary generation code
2. Verify that data is being saved to Supabase by checking your Supabase dashboard
3. Go to **Table Editor** in Supabase to see your data

## Step 9: Clean Up (Optional)

Once you've verified everything works:

1. **Backup your SQLite database** (just in case):
   ```bash
   cp vocab.db vocab.db.backup
   ```

2. You can remove the SQLite database and migration script:
   ```bash
   rm vocab.db
   rm migrate_to_supabase.py
   ```

## Benefits of Supabase

✅ **Cloud-hosted**: No need to manage database files  
✅ **Scalable**: Handles multiple users and large datasets  
✅ **Real-time**: Built-in real-time subscriptions  
✅ **SQL**: Full PostgreSQL power with complex queries  
✅ **Dashboard**: Easy data management through web interface  
✅ **Backup**: Automatic backups and point-in-time recovery  
✅ **Security**: Built-in authentication and row-level security  

## Troubleshooting

### Connection Issues
- Verify your `SUPABASE_URL` and `SUPABASE_ANON_KEY` are correct
- Check that your Supabase project is active (not paused)
- Ensure tables were created successfully

### Migration Issues
- Make sure your SQLite database (`vocab.db`) exists
- Verify table structures match between SQLite and Supabase
- Check for any data type mismatches

### Performance Issues
- Consider adding more indexes for your query patterns
- Use Supabase's built-in caching features
- Monitor query performance in the Supabase dashboard

## Support

- [Supabase Documentation](https://supabase.com/docs)
- [Supabase Community](https://github.com/supabase/supabase/discussions)
- [Python Client Documentation](https://supabase.com/docs/reference/python)

Your vocabulary application is now powered by Supabase! 🚀