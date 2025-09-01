from models import VocabEntry, CEFRLevel, VocabGenerationResponse, PartOfSpeech
from topics import get_topic_list, get_categories, get_topics_by_category
from typing_extensions import TypedDict
from typing import List
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from supabase_database import SupabaseVocabDatabase
from config import Config
import os

# Validate configuration
Config.validate()

# Set up environment variables
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGCHAIN_API_KEY"] = Config.LANGSMITH_API_KEY
os.environ["LANGCHAIN_PROJECT"] = Config.LANGSMITH_PROJECT
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

# =========== LLM ===========
llm = ChatOpenAI(
    model=Config.LLM_MODEL,
    temperature=Config.TOPIC_FOCUS_TEMPERATURE,  # Use topic-focused temperature
    api_key=Config.OPENAI_API_KEY
)

# =========== Database ===========
db = SupabaseVocabDatabase()

# =========== State ===========
class State(TypedDict):
	topic: str
	level: CEFRLevel
	target_language: str
	original_langauge: str
	vocab_list: list[str]
	vocab_entries: list[VocabEntry]


structured_llm = llm.with_structured_output(VocabGenerationResponse)

# =========== Nodes - functions ===========

def filter_duplicates(entries: List[VocabEntry], existing_combinations: List[tuple]) -> List[VocabEntry]:
    """Filter out entries that already exist in the database"""
    filtered_entries = []
    for entry in entries:
        # Create combination key: (word, level, part_of_speech)
        entry_key = (entry.word.lower(), entry.level.value, entry.part_of_speech.value if entry.part_of_speech else None)
        
        if entry_key not in [(combo[0].lower(), combo[1], combo[2]) for combo in existing_combinations]:
            filtered_entries.append(entry)
        else:
            print(f"Filtered out duplicate: {entry.word} ({entry.part_of_speech.value if entry.part_of_speech else 'unknown'})")
    return filtered_entries

def get_existing_combinations_for_topic(topic_name: str, category_name: str = None) -> List[tuple]:
    """Get existing word combinations for a topic to avoid duplicates"""
    return db.get_existing_combinations(topic_name=topic_name, category_name=category_name)

def validate_topic_relevance(entries: List[VocabEntry], topic_name: str) -> List[VocabEntry]:
    """Validate that entries are relevant to the given topic"""
    relevant_entries = []
    topic_lower = topic_name.lower()
    
    # Keywords that indicate off-topic content (very generic words)
    generic_words = [
        'hello', 'goodbye', 'thank you', 'please', 'yes', 'no', 'maybe',
        'big', 'small', 'good', 'bad', 'happy', 'sad', 'fast', 'slow',
        'eat', 'drink', 'sleep', 'walk', 'run', 'talk', 'listen', 'see',
        'book', 'pen', 'paper', 'table', 'chair', 'door', 'window'
    ]
    
    # Topic-specific vocabulary patterns (words that are clearly related)
    topic_patterns = {
        'shopping': ['shop', 'buy', 'sell', 'price', 'cost', 'discount', 'sale', 'store', 'market', 'mall', 'cart', 'checkout', 'receipt', 'cash', 'card', 'money', 'bargain', 'deal', 'brand', 'size', 'fit', 'return', 'exchange', 'gift', 'purchase', 'spend', 'save', 'budget', 'expensive', 'cheap', 'affordable'],
        'food': ['food', 'eat', 'drink', 'cook', 'recipe', 'ingredient', 'meal', 'dish', 'cuisine', 'restaurant', 'kitchen', 'taste', 'flavor', 'spice', 'seasoning', 'fresh', 'delicious', 'hungry', 'thirsty', 'breakfast', 'lunch', 'dinner', 'snack'],
        'technology': ['tech', 'computer', 'phone', 'device', 'app', 'software', 'hardware', 'digital', 'online', 'internet', 'data', 'information', 'system', 'program', 'code', 'algorithm', 'database', 'network', 'connect', 'download', 'upload', 'install', 'update'],
        'business': ['business', 'company', 'work', 'office', 'meeting', 'project', 'team', 'manager', 'employee', 'client', 'customer', 'service', 'product', 'market', 'industry', 'profit', 'revenue', 'cost', 'budget', 'plan', 'strategy', 'goal', 'target'],
        'travel': ['travel', 'trip', 'journey', 'destination', 'hotel', 'flight', 'airport', 'ticket', 'booking', 'reservation', 'tourist', 'vacation', 'holiday', 'sightseeing', 'tour', 'guide', 'passport', 'visa', 'luggage', 'suitcase', 'map', 'direction']
    }
    
    for entry in entries:
        word_lower = entry.word.lower()
        definition_lower = entry.definition.lower()
        
        # Check if word is too generic
        if word_lower in generic_words:
            print(f"Filtered out generic word: {entry.word}")
            continue
            
        # Check if definition mentions the topic
        if topic_lower in definition_lower:
            relevant_entries.append(entry)
            continue
            
        # Check if word is clearly related to topic using topic patterns
        if topic_lower in topic_patterns:
            topic_keywords = topic_patterns[topic_lower]
            if any(keyword in word_lower for keyword in topic_keywords):
                relevant_entries.append(entry)
                continue
        
        # Fallback: check if any word from topic name appears in definition
        topic_keywords = topic_lower.split()
        if any(keyword in definition_lower for keyword in topic_keywords):
            relevant_entries.append(entry)
            continue
            
        # If we get here, the word might not be relevant
        print(f"Note: Checking relevance for '{entry.word}' in topic '{topic_name}'")
        relevant_entries.append(entry)  # Keep it for now, let user decide
    
    return relevant_entries

def run_continuous_vocab_generation(
    topics: List[str] = None,
    category: str = None,
    level: CEFRLevel = CEFRLevel.A2,
    language_to_learn: str = "English",
    learners_native_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 5,
    idioms_per_batch: int = 5,
    delay_seconds: int = 3,
    save_topic_list: bool = False,
    topic_list_name: str = None
):
    """
    Run continuous vocabulary generation for multiple topics and different types.
    
    Args:
        topics: List of specific topics to process (if None, uses category)
        category: Category of topics to process (if None, uses topics list)
        level: CEFR level (default: A2)
        language_to_learn: Language to translate to (default: Vietnamese)
        learners_native_language: Source language (default: English)
        vocab_per_batch: Number of vocabularies to generate per batch (default: 10)
        phrasal_verbs_per_batch: Number of phrasal verbs to generate per batch (default: 5)
        idioms_per_batch: Number of idioms to generate per batch (default: 5)
        delay_seconds: Delay between batches in seconds (default: 3)
        save_topic_list: Whether to save the topic list to database (default: False)
        topic_list_name: Custom name for the topic list (default: auto-generated)
    """
    import time
    import signal
    import sys
    
    # Determine topics to process
    if topics:
        topic_list = topics
    elif category:
        topic_list = get_topic_list(category)
    else:
        topic_list = ["shopping"] 
    
    # Save topic list to database if requested
    if save_topic_list and topics:  # Only save custom topic lists, not category-based ones
        db.save_topic_list(
            topics=topic_list,
            list_name=topic_list_name,
            category=category,
            level=level,
            target_language=language_to_learn,
            original_language=learners_native_language
        )
    
    print(f"Topics to process: {len(topic_list)}")
    for i, topic in enumerate(topic_list, 1):
        print(f"{i}. {topic}")
    print()
    
    # Flag to control the loop
    running = True
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C to gracefully stop the loop"""
        nonlocal running
        print("\n\nStopping vocabulary generation...")
        running = False
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    batch_count = 0
    topic_index = 0
    current_topic = topic_list[0]
    
    print(f"Starting continuous vocabulary generation")
    print(f"Level: {level.value}, Target Language: {language_to_learn}")
    print("Press Ctrl+C to stop\n")
    
    try:
        while running and topic_index < len(topic_list):
            batch_count += 1
            current_topic = topic_list[topic_index]
            
            print(f"\n{'='*60}")
            print(f"BATCH #{batch_count} - TOPIC: {current_topic} ({topic_index + 1}/{len(topic_list)})")
            print(f"{'='*60}")
            
            # Get existing combinations for content polling (not for filtering AI output)
            existing_combinations = get_existing_combinations_for_topic(current_topic, category)
            print(f"Found {len(existing_combinations)} existing combinations in database")
            
            # Create simplified, focused prompt
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {current_topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{current_topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            try:
                # Generate vocabulary using structured output
                res = structured_llm.invoke(prompt)
                
                # Combine all entries
                all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
                
                print(f"Generated:")
                print(f"- {len(res.vocabularies)} vocabularies")
                print(f"- {len(res.phrasal_verbs)} phrasal verbs")
                print(f"- {len(res.idioms)} idioms")
                print(f"Total: {len(all_entries)} entries")
                
                # Validate topic relevance
                print(f"\nValidating topic relevance for '{current_topic}'...")
                relevant_entries = validate_topic_relevance(all_entries, current_topic)
                print(f"Topic-relevant entries: {len(relevant_entries)}/{len(all_entries)}")
                
                # Show generated entries
                for i, entry in enumerate(relevant_entries[:5]):  # Show first 5
                    pos = entry.part_of_speech.value if entry.part_of_speech else "unknown"
                    print(f"  {i+1}. {entry.word} ({pos}): {entry.definition}")
                
                # Filter out duplicates
                filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
                
                if filtered_entries:
                    print(f"\nSaving {len(filtered_entries)} new entries to database...")
                    
                    # Save to database
                    db.insert_vocab_entries(
                        entries=filtered_entries,
                        topic_name=current_topic,
                        category_name=category,
                        target_language=language_to_learn,
                        original_language=learners_native_language
                    )
                    print("Saved successfully!")
                else:
                    print("\nNo new entries to save (all were duplicates)")
                
                # Get updated count for this topic
                saved_entries = db.get_vocab_entries(topic_name=current_topic, category_name=category)
                print(f"Total entries in database for '{current_topic}': {len(saved_entries)}")
                
            except Exception as e:
                print(f"Error in batch #{batch_count}: {e}")
                print("Continuing to next topic...")
            
            # Move to next topic
            topic_index += 1
            
            # Add delay between topics (except for the last one)
            if topic_index < len(topic_list) and running:
                print(f"\n⏳ Waiting {delay_seconds} seconds before next topic...")
                time.sleep(delay_seconds)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
    
    # Final summary
    total_entries = len(db.get_vocab_entries())
    print(f"\nFINAL SUMMARY:")
    print(f"Topics processed: {topic_index}/{len(topic_list)}")
    print(f"Level: {level.value}")
    print(f"Total batches run: {batch_count}")
    print(f"Total entries in database: {total_entries}")
    print("Done!")
    
    return {
        "success": True,
        "topics_processed": topic_index,
        "total_topics": len(topic_list),
        "batches_run": batch_count,
        "entries_created": total_entries
    }

def view_saved_topic_lists():
    """View all saved topic lists"""
    topic_lists = db.get_topic_lists()
    
    if not topic_lists:
        print("No saved topic lists found.")
        return
    
    print(f"Found {len(topic_lists)} saved topic lists:")
    print("=" * 60)
    
    for i, topic_list in enumerate(topic_lists, 1):
        print(f"{i}. {topic_list['list_name']}")
        print(f"   Topics: {', '.join(topic_list['topics'])}")
        print(f"   Level: {topic_list['level']}")
        print(f"   Category: {topic_list['category'] or 'Custom'}")
        print(f"   Created: {topic_list['created_at']}")
        print()

def run_single_topic_generation(
    topic: str,
    level: CEFRLevel = CEFRLevel.A2,
    language_to_learn: str = "English",
    learners_native_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 5,
    idioms_per_batch: int = 5,
    delay_seconds: int = 3,
    save_topic_list: bool = False,
    topic_list_name: str = None
):
    """
    Generate vocabulary for a single topic
    """
    return run_continuous_vocab_generation(
        topics=[topic],
        level=level,
        language_to_learn=language_to_learn,
        learners_native_language=learners_native_language,
        vocab_per_batch=vocab_per_batch,
        phrasal_verbs_per_batch=phrasal_verbs_per_batch,
        idioms_per_batch=idioms_per_batch,
        delay_seconds=delay_seconds,
        save_topic_list=save_topic_list,
        topic_list_name=topic_list_name
    )
