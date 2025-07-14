# AI Vocabulary Generator

This system automatically creates vocabulary content for language learning.

## How It Works

1. You give it a topic (like "shopping" or "food").
2. It generates vocabulary words, phrases, and expressions for that topic.
3. It provides definitions, translations, and examples for each word.
4. It saves everything in a database for you to use.

## Features

- **Multiple topics**: Choose from 10 categories with 100+ topics.
- **Custom topics**: Use any topic you want.
- **Different levels**: Beginner to advanced difficulty.
- **No duplicates**: Smart system prevents repeating words.
- **Rich content**: Definitions, translations, and examples.
- **Easy storage**: Everything saved in a database.

## How to Test

### 1. Setup
```bash
pip install fastapi langgraph langchain-openai pydantic python-dotenv
```

Create a `.env` file:

Replace with your OPENAI_API_KEY
Use the other keys as default

```
OPENAI_API_KEY=your_openai_api_key
LANGSMITH_PROJECT=polynot
LANGSMITH_API_KEY=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
```

### 2. Test with a Single Topic


#### Tests are written in vocab_agent.py but feel free to write your own


```python
from vocab_agent import run_single_topic_generation

run_single_topic_generation("shopping")
```

### 3. Test with a Category
```python
from vocab_agent import run_continuous_vocab_generation

run_continuous_vocab_generation(
    category="daily_life",
    level=CEFRLevel.A2
)
```

### 4. Test with Custom Topics
```python
run_continuous_vocab_generation(
    topics=["food", "travel", "technology"],
    level=CEFRLevel.B1
)
```

### 5. Check Results
```python
from database import VocabDatabase

db = VocabDatabase()
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
