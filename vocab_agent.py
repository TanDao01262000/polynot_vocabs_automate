from models import VocabEntry, CEFRLevel, VocabListResponse, PartOfSpeech
from topics import get_topic_list, get_categories, get_topics_by_category
from typing_extensions import TypedDict
from typing import List
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from database import VocabDatabase
import os
from dotenv import load_dotenv
load_dotenv(override=True)
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "polynot")
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

# =========== LLM ===========
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY")
)

# =========== Database ===========
db = VocabDatabase()

# =========== State ===========
class State(TypedDict):
	topic: str
	level: CEFRLevel
	target_language: str
	original_langauge: str
	vocab_list: list[str]
	vocab_entries: list[VocabEntry]


structured_llm = llm.with_structured_output(VocabListResponse)

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

def get_existing_combinations_for_topic(topic: str) -> List[tuple]:
    """Get existing word combinations for a topic to avoid duplicates"""
    return db.get_existing_combinations(topic=topic)

def run_continuous_vocab_generation(
    topics: List[str] = None,
    category: str = None,
    level: CEFRLevel = CEFRLevel.A2,
    target_language: str = "Vietnamese",
    original_language: str = "English",
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
        target_language: Language to translate to (default: Vietnamese)
        original_language: Source language (default: English)
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
            target_language=target_language,
            original_language=original_language
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
    print(f"Level: {level.value}, Target Language: {target_language}")
    print("Press Ctrl+C to stop\n")
    
    try:
        while running and topic_index < len(topic_list):
            batch_count += 1
            current_topic = topic_list[topic_index]
            
            print(f"\n{'='*60}")
            print(f"BATCH #{batch_count} - TOPIC: {current_topic} ({topic_index + 1}/{len(topic_list)})")
            print(f"{'='*60}")
            
            # Get existing combinations to avoid duplicates
            existing_combinations = get_existing_combinations_for_topic(current_topic)
            print(f"Found {len(existing_combinations)} existing combinations in database")
            
            # Create comprehensive prompt
            if existing_combinations:
                existing_words_str = ", ".join([f"{combo[0]} ({combo[2]})" for combo in existing_combinations[:20]])
                prompt = f'''Based on the topic of {current_topic}, generate:

1. {vocab_per_batch} NEW vocabularies (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} NEW phrasal verbs
3. {idioms_per_batch} NEW idioms

At CEFR level {level.value}. Original language is {original_language}. Target language is {target_language}.

CRITICAL: You MUST avoid these existing words completely: {existing_words_str}

Instructions:
1. Generate ONLY words that are NOT in the existing list above
2. Focus on different aspects of {current_topic}
3. Include a variety of parts of speech
4. Be creative and think of less common but relevant vocabulary
5. For phrasal verbs, focus on common combinations used in {current_topic} context
6. For idioms, include expressions commonly used when discussing {current_topic}

For each entry, specify the part of speech (noun, verb, adjective, adverb, phrasal_verb, idiom, phrase).'''
            else:
                prompt = f'''Based on the topic of {current_topic}, generate:

1. {vocab_per_batch} vocabularies (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} phrasal verbs
3. {idioms_per_batch} idioms

At CEFR level {level.value}. Original language is {original_language}. Target language is {target_language}.

For each entry, specify the part of speech (noun, verb, adjective, adverb, phrasal_verb, idiom, phrase).'''
            
            try:
                res = structured_llm.invoke(prompt)
                
                # Process all types of entries
                all_entries = []
                all_entries.extend(res.vocabularies)
                all_entries.extend(res.phrasal_verbs)
                all_entries.extend(res.idioms)
                
                print(f"Generated:")
                print(f"- {len(res.vocabularies)} vocabularies")
                print(f"- {len(res.phrasal_verbs)} phrasal verbs")
                print(f"- {len(res.idioms)} idioms")
                print(f"Total: {len(all_entries)} entries")
                
                # Show some examples
                for i, entry in enumerate(all_entries[:5]):  # Show first 5
                    pos = entry.part_of_speech.value if entry.part_of_speech else "unknown"
                    print(f"  {i+1}. {entry.word} ({pos}): {entry.definition}")
                
                # Filter duplicates before saving
                filtered_entries = filter_duplicates(all_entries, existing_combinations)
                
                if filtered_entries:
                    # Save to database
                    print(f"\nSaving {len(filtered_entries)} new entries to database...")
                    db.insert_vocab_entries(
                        entries=filtered_entries,
                        topic=current_topic,
                        target_language=target_language,
                        original_language=original_language
                    )
                    print("✓ Saved successfully!")
                else:
                    print("\n⚠️  No new entries to save (all were duplicates)")
                
                # Show current database stats
                saved_entries = db.get_vocab_entries(topic=current_topic)
                print(f"📊 Total entries in database for '{current_topic}': {len(saved_entries)}")
                
                # Move to next topic
                topic_index += 1
                
            except Exception as e:
                print(f"❌ Error in batch #{batch_count}: {e}")
                print("Continuing to next topic...")
                topic_index += 1
            
            # Wait a bit before next batch to avoid rate limits
            if running and topic_index < len(topic_list):
                print(f"\n⏳ Waiting {delay_seconds} seconds before next topic...")
                time.sleep(delay_seconds)
    
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
    
    finally:
        # Final summary
        total_entries = 0
        for topic in topic_list:
            saved_entries = db.get_vocab_entries(topic=topic)
            total_entries += len(saved_entries)
        
        print(f"\n📈 FINAL SUMMARY:")
        print(f"Topics processed: {topic_index}/{len(topic_list)}")
        print(f"Level: {level.value}")
        print(f"Total batches run: {batch_count}")
        print(f"Total entries in database: {total_entries}")
        print("Done!")

def view_saved_topic_lists():
    """View all saved topic lists from the database"""
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
    target_language: str = "Vietnamese",
    original_language: str = "English",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 5,
    idioms_per_batch: int = 5,
    delay_seconds: int = 3
):
    """Run generation for a single topic (backward compatibility)"""
    return run_continuous_vocab_generation(
        topics=[topic],
        level=level,
        target_language=target_language,
        original_language=original_language,
        vocab_per_batch=vocab_per_batch,
        phrasal_verbs_per_batch=phrasal_verbs_per_batch,
        idioms_per_batch=idioms_per_batch,
        delay_seconds=delay_seconds
    )

if __name__ == '__main__':
    # Example 1: Generate for a specific category (not saved)
    # print("=== Example 1: Daily Life Topics ===")
    # run_continuous_vocab_generation(
    #     category="daily_life",
    #     level=CEFRLevel.A2,
    #     vocab_per_batch=8,
    #     phrasal_verbs_per_batch=4,
    #     idioms_per_batch=3,
    #     delay_seconds=2
    # )
    
    # Example 2: Generate for custom topics and save the list
    print("\n=== Example 2: Custom Topics (Saved) ===")
    run_continuous_vocab_generation(
        topics=["gameshow", "video game", "music"],
        level=CEFRLevel.B1,
        vocab_per_batch=15,
        phrasal_verbs_per_batch=3,
        idioms_per_batch=2,
        delay_seconds=1,
        save_topic_list=True,  # Save this custom list
        topic_list_name="my_custom_list"
    )
    
    # Example 3: View saved topic lists
    print("\n=== Example 3: View Saved Topic Lists ===")
    view_saved_topic_lists()
    
    # Example 4: Single topic (not saved)
    # print("\n=== Example 4: Single Topic ===")
    # run_single_topic_generation(
    #     topic="technology",
    #     level=CEFRLevel.B2,
    #     vocab_per_batch=12,
    #     phrasal_verbs_per_batch=6,
    #     idioms_per_batch=4
    # )
