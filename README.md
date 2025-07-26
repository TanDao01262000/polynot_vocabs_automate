# AI Vocabulary Generator

This system automatically creates vocabulary content for language learning using AI and stores data in Supabase.

## How It Works

1. You give it a topic (like "shopping" or "food").
2. It generates vocabulary words, phrases, and expressions for that topic.
3. It provides definitions, translations, and examples for each word.
4. It saves everything in a Supabase database for you to use.

## Features

- **Multiple topics**: Choose from 10 categories with 100+ topics.
- **Custom topics**: Use any topic you want.
- **Different levels**: Beginner to advanced difficulty.
- **No duplicates**: Smart system prevents repeating words.
- **Rich content**: Definitions, translations, and examples.
- **Cloud storage**: Everything saved in Supabase database.
- **Real-time sync**: Data is immediately available across devices.

## Setup

### 1. Install Dependencies
```bash
pip install -r requiments.txt
```

### 2. Environment Configuration
Create a `.env` file with your credentials:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# LangSmith Configuration (optional)
LANGSMITH_PROJECT=polynot
LANGSMITH_API_KEY=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

# Supabase Configuration (required)
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key

# Optional: Customize defaults
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.7
DEFAULT_TARGET_LANGUAGE=Vietnamese
DEFAULT_ORIGINAL_LANGUAGE=English
DEFAULT_VOCAB_PER_BATCH=10
DEFAULT_PHRASAL_VERBS_PER_BATCH=5
DEFAULT_IDIOMS_PER_BATCH=5
DEFAULT_DELAY_SECONDS=3
```

### 3. Supabase Setup
1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Run the SQL schema in your Supabase SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create tables
CREATE TABLE vocab_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  word TEXT NOT NULL,
  definition TEXT NOT NULL,
  translation TEXT NOT NULL,
  example TEXT NOT NULL,
  example_translation TEXT NOT NULL,
  level TEXT NOT NULL,
  part_of_speech TEXT,
  topic TEXT NOT NULL,
  target_language TEXT NOT NULL,
  original_language TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(word, topic, level, part_of_speech)
);

CREATE TABLE topic_lists(
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  list_name TEXT NOT NULL,
  topics JSONB NOT NULL,
  category TEXT,
  level TEXT NOT NULL,
  target_language TEXT,
  original_language TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
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

-- Create triggers
CREATE TRIGGER update_vocab_entries_updated_at
  BEFORE UPDATE ON vocab_entries
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_topic_lists_updated_at
  BEFORE UPDATE ON topic_lists
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

3. Get your Supabase URL and anon key from the project settings

### 4. Test Supabase Integration
```bash
python test_supabase.py
```

### 5. Migrate from SQLite (if applicable)
If you have existing data in the SQLite database:
```bash
python migrate_to_supabase.py
```

## How to Test

### 1. Test with a Single Topic
```python
from vocab_agent import run_single_topic_generation

run_single_topic_generation("shopping")
```

### 2. Test with a Category
```python
from vocab_agent import run_continuous_vocab_generation

run_continuous_vocab_generation(
    category="daily_life",
    level=CEFRLevel.A2
)
```

### 3. Test with Custom Topics
```python
run_continuous_vocab_generation(
    topics=["food", "travel", "technology"],
    level=CEFRLevel.B1
)
```

### 4. Check Results
```python
from supabase_database import SupabaseVocabDatabase

db = SupabaseVocabDatabase()
entries = db.get_vocab_entries(topic="shopping")
print(f"Found {len(entries)} vocabulary entries")
```

## Available Categories

- `daily_life`: Shopping, food, family, home, work
- `business_professional`: Business, marketing, finance, management
- `academic_education`: Education, learning, research, teaching
- `technology_digital`: Software, programming, AI, cybersecurity
- `travel_tourism`: Travel, transportation, tourism, destinations
- `health_wellness`: Health, fitness, medical care, nutrition
- `entertainment_media`: Movies, music, gaming, performing arts
- `sports_fitness`: Sports, training, competition, athletics
- `social_relationships`: Relationships, communication, social events
- `environment_nature`: Environment, nature, sustainability, wildlife

## What You Get

Each vocabulary entry includes:
- The word
- Definition in English
- Translation to target language
- Example sentence
- Difficulty level
- Part of speech

## Database Features

### Supabase Integration
- **Real-time data**: Changes are immediately reflected
- **Scalable**: Handles large amounts of vocabulary data
- **Secure**: Built-in authentication and authorization
- **Backup**: Automatic backups and point-in-time recovery
- **API**: RESTful API for external integrations

### Data Management
- **Duplicate prevention**: Smart detection of existing words
- **Topic organization**: Group vocabulary by topics and categories
- **Level filtering**: Filter by CEFR levels (A1-C2)
- **Search functionality**: Full-text search across words and definitions
- **Statistics**: Get insights about your vocabulary collection

## Troubleshooting

### Common Issues

1. **Supabase connection failed**
   - Check your `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `.env`
   - Verify your Supabase project is active

2. **OpenAI API errors**
   - Ensure your `OPENAI_API_KEY` is valid and has sufficient credits
   - Check rate limits if you're generating large amounts of content

3. **Migration issues**
   - Run `python test_supabase.py` first to verify connection
   - Check that your Supabase schema matches the provided SQL

### Getting Help

- Run `python test_supabase.py` to diagnose connection issues
- Check the Supabase dashboard for database errors
- Verify all environment variables are set correctly
