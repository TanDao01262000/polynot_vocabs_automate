from models import VocabEntry, CEFRLevel, VocabGenerationResponse, PartOfSpeech
from topics import get_topic_list, get_categories, get_topics_by_category
from typing_extensions import TypedDict
from typing import List
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from supabase_database import SupabaseVocabDatabase
from config import Config
from langchain_tavily import TavilySearch
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
    request_timeout=60,  # Increase timeout for complex operations
    api_key=Config.OPENAI_API_KEY
)

# =========== Database ===========
db = SupabaseVocabDatabase()

# =========== Search Tool Disabled ===========
# Search tool was making vocabulary generation worse
# Using direct creative generation instead
print("🔧 Search tool disabled - using direct creative generation")

# =========== Search Functions Disabled ===========
def search_for_topic_context(topic: str, level: str = None, language: str = "English") -> str:
    """Search function disabled - using direct creative generation"""
    print("🔧 Search function disabled - using direct creative generation")
    return ""

# =========== State ===========
class State(TypedDict):
	topic: str
	level: CEFRLevel
	target_language: str
	original_langauge: str
	vocab_list: list[str]
	vocab_entries: list[VocabEntry]
	vocab_per_batch: int  # Add batch parameters
	phrasal_verbs_per_batch: int
	idioms_per_batch: int


structured_llm = llm.with_structured_output(VocabGenerationResponse)

# =========== Nodes - functions ===========

def filter_duplicates(entries: List[VocabEntry], existing_combinations: List[tuple]) -> List[VocabEntry]:
    """Filter out entries that already exist in the database (less aggressive)"""
    filtered_entries = []
    existing_keys = [(combo[0].lower(), combo[1], combo[2]) for combo in existing_combinations]
    
    print(f"🔍 Checking {len(entries)} entries against {len(existing_combinations)} existing combinations")
    
    for entry in entries:
        # Create combination key: (word, level, part_of_speech)
        entry_key = (entry.word.lower(), entry.level.value, entry.part_of_speech.value if entry.part_of_speech else None)
        
        if entry_key not in existing_keys:
            filtered_entries.append(entry)
        else:
            print(f"Filtered out duplicate: {entry.word} ({entry.part_of_speech.value if entry.part_of_speech else 'unknown'})")
    
    print(f"🔍 Duplicate filtering: {len(entries)} → {len(filtered_entries)} entries")
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
    topic_list_name: str = None,
):
    """
    Run continuous vocabulary generation using LangGraph workflow
    Now properly integrates search agent -> vocabulary generation flow
    """
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
            
            # Direct generation with 1.5x multiplier and retry logic
            # Apply 1.5x multiplier to ensure we have enough entries after filtering
            target_vocab = int(vocab_per_batch * 1.5)
            target_phrasal = int(phrasal_verbs_per_batch * 1.5)
            target_idioms = int(idioms_per_batch * 1.5)
            
            print(f"🔧 Creating STANDARD prompt with 1.5x multiplier")
            print(f"📊 Requesting: {target_vocab} vocab, {target_phrasal} phrasal, {target_idioms} idioms")
            print(f"📊 Target after filtering: {vocab_per_batch} vocab, {phrasal_verbs_per_batch} phrasal, {idioms_per_batch} idioms")
            
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

STRICT COUNT REQUIREMENTS:
- Generate EXACTLY {target_vocab} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
- Generate EXACTLY {target_phrasal} {language_to_learn} phrasal verbs/expressions  
- Generate EXACTLY {target_idioms} {language_to_learn} idioms/proverbs

QUALITY REQUIREMENTS:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic
- Generate diverse, engaging, and useful vocabulary

CRITICAL VALIDATION:
- You MUST generate exactly the specified number of items in each category
- Count your results carefully before responding
- If you don't have the exact count, retry and generate more
- Do not generate more or fewer than requested

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            try:
                # Generate vocabulary using structured output with count validation
                max_attempts = 3
                attempt = 0
                
                while attempt < max_attempts:
                    attempt += 1
                    print(f"🔄 Generation attempt {attempt}/{max_attempts}")
                    
                    res = structured_llm.invoke(prompt)
                    
                    # Validate counts against 1.5x targets
                    vocab_count = len(res.vocabularies)
                    phrasal_count = len(res.phrasal_verbs)
                    idiom_count = len(res.idioms)
                    
                    print(f"📊 Generated counts:")
                    print(f"   Vocabularies: {vocab_count}/{target_vocab} (target: {vocab_per_batch})")
                    print(f"   Phrasal verbs: {phrasal_count}/{target_phrasal} (target: {phrasal_verbs_per_batch})")
                    print(f"   Idioms: {idiom_count}/{target_idioms} (target: {idioms_per_batch})")
                    
                    # Check if counts match 1.5x requirements
                    counts_match = (
                        vocab_count == target_vocab and
                        phrasal_count == target_phrasal and
                        idiom_count == target_idioms
                    )
                    
                    if counts_match:
                        print("✅ All counts match requirements!")
                        break
                    else:
                        print(f"⚠️ Count mismatch detected. Attempt {attempt}/{max_attempts}")
                        if attempt < max_attempts:
                            # Add more specific instructions for retry
                            prompt += f"\n\nRETRY INSTRUCTION: Previous attempt generated {vocab_count} vocabularies, {phrasal_count} phrasal verbs, and {idiom_count} idioms. You need exactly {target_vocab} vocabularies, {target_phrasal} phrasal verbs, and {target_idioms} idioms. Please count carefully and generate the exact numbers requested."
                        else:
                            print("❌ Max attempts reached. Using generated results as-is.")
                
                # Combine all entries
                all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
                
                print(f"Final generated counts:")
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
                
                # Filter out duplicates and limit to requested counts
                filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
                
                # Limit to requested counts (take first N of each type)
                final_entries = []
                vocab_added = 0
                phrasal_added = 0
                idiom_added = 0
                
                for entry in filtered_entries:
                    if entry.part_of_speech.value == 'phrasal_verb' and phrasal_added < phrasal_verbs_per_batch:
                        final_entries.append(entry)
                        phrasal_added += 1
                    elif entry.part_of_speech.value == 'idiom' and idiom_added < idioms_per_batch:
                        final_entries.append(entry)
                        idiom_added += 1
                    elif entry.part_of_speech.value not in ['phrasal_verb', 'idiom'] and vocab_added < vocab_per_batch:
                        final_entries.append(entry)
                        vocab_added += 1
                
                print(f"\n📊 Final counts after filtering:")
                print(f"   Vocabularies: {vocab_added}/{vocab_per_batch}")
                print(f"   Phrasal verbs: {phrasal_added}/{phrasal_verbs_per_batch}")
                print(f"   Idioms: {idiom_added}/{idioms_per_batch}")
                
                if final_entries:
                    print(f"\nSaving {len(final_entries)} new entries to database...")
                    
                    # Save to database
                    db.insert_vocab_entries(
                        entries=final_entries,
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

# =========== LangGraph Nodes ===========

def search_node(state: State) -> State:
    """Search node disabled - using direct creative generation"""
    print("🔧 Search node disabled - using direct creative generation")
    return state

def generation_node(state: State) -> State:
    """Simple, effective vocabulary generation with count constraints and 1.5x multiplier"""
    topic = state["topic"]
    level = state["level"]
    target_language = state["target_language"]
    original_language = state["original_langauge"]
    
    # Get batch parameters from state
    vocab_per_batch = state.get("vocab_per_batch", 10)
    phrasal_verbs_per_batch = state.get("phrasal_verbs_per_batch", 5)
    idioms_per_batch = state.get("idioms_per_batch", 5)
    
    # Apply 1.5x multiplier to ensure we have enough entries after filtering
    target_vocab = int(vocab_per_batch * 1.5)
    target_phrasal = int(phrasal_verbs_per_batch * 1.5)
    target_idioms = int(idioms_per_batch * 1.5)
    
    print(f"🎯 Generation node: Creating vocabulary for '{topic}'")
    print(f"📊 Requesting: {target_vocab} vocab, {target_phrasal} phrasal verbs, {target_idioms} idioms")
    print(f"📊 Target after filtering: {vocab_per_batch} vocab, {phrasal_verbs_per_batch} phrasal verbs, {idioms_per_batch} idioms")
    
    # Enhanced prompt with strict count requirements and 1.5x multiplier
    prompt = f'''You are an expert {target_language} language teacher. Generate vocabulary for "{topic}" at {level.value} level.

STRICT COUNT REQUIREMENTS:
- Generate EXACTLY {target_vocab} vocabulary words (nouns, verbs, adjectives, adverbs)
- Generate EXACTLY {target_phrasal} phrasal verbs/expressions
- Generate EXACTLY {target_idioms} idioms/proverbs

QUALITY REQUIREMENTS:
- All words must be directly relevant to "{topic}"
- Ensure appropriate difficulty for {level.value} level
- Generate diverse, engaging, and useful vocabulary
- Avoid repetition and generic terms
- Include clear, detailed definitions
- Provide realistic example sentences
- Ensure accurate translations

CRITICAL VALIDATION:
- You MUST generate exactly the specified number of items in each category
- Count your results carefully before responding
- If you don't have the exact count, retry and generate more
- Do not generate more or fewer than requested

For each entry, include:
- word: the vocabulary word
- definition: clear definition in {target_language}
- example: practical example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: part of speech (noun, verb, adjective, adverb, etc.)

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
    
    try:
        import time
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"🔄 Generation attempt {attempt}/{max_attempts}")
            
            llm_start = time.time()
            res = structured_llm.invoke(prompt)
            llm_time = time.time() - llm_start
            print(f"⏱️ Generation completed in {llm_time:.2f} seconds")
            
            # Validate counts against 1.5x targets
            vocab_count = len(res.vocabularies)
            phrasal_count = len(res.phrasal_verbs)
            idiom_count = len(res.idioms)
            
            print(f"📊 Generated counts:")
            print(f"   Vocabularies: {vocab_count}/{target_vocab} (target: {vocab_per_batch})")
            print(f"   Phrasal verbs: {phrasal_count}/{target_phrasal} (target: {phrasal_verbs_per_batch})")
            print(f"   Idioms: {idiom_count}/{target_idioms} (target: {idioms_per_batch})")
            
            # Check if counts match 1.5x requirements
            counts_match = (
                vocab_count == target_vocab and
                phrasal_count == target_phrasal and
                idiom_count == target_idioms
            )
            
            if counts_match:
                print("✅ All counts match requirements!")
                break
            else:
                print(f"⚠️ Count mismatch detected. Attempt {attempt}/{max_attempts}")
                if attempt < max_attempts:
                    # Add more specific instructions for retry
                    prompt += f"\n\nRETRY INSTRUCTION: Previous attempt generated {vocab_count} vocabularies, {phrasal_count} phrasal verbs, and {idiom_count} idioms. You need exactly {target_vocab} vocabularies, {target_phrasal} phrasal verbs, and {target_idioms} idioms. Please count carefully and generate the exact numbers requested."
                else:
                    print("❌ Max attempts reached. Using generated results as-is.")
        
        # Combine all entries from structured response
        all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
        
        # Limit to requested counts (take first N of each type)
        final_entries = []
        vocab_added = 0
        phrasal_added = 0
        idiom_added = 0
        
        for entry in all_entries:
            if entry.part_of_speech.value == 'phrasal_verb' and phrasal_added < phrasal_verbs_per_batch:
                final_entries.append(entry)
                phrasal_added += 1
            elif entry.part_of_speech.value == 'idiom' and idiom_added < idioms_per_batch:
                final_entries.append(entry)
                idiom_added += 1
            elif entry.part_of_speech.value not in ['phrasal_verb', 'idiom'] and vocab_added < vocab_per_batch:
                final_entries.append(entry)
                vocab_added += 1
        
        print(f"📊 Final counts after filtering:")
        print(f"   Vocabularies: {vocab_added}/{vocab_per_batch}")
        print(f"   Phrasal verbs: {phrasal_added}/{phrasal_verbs_per_batch}")
        print(f"   Idioms: {idiom_added}/{idioms_per_batch}")
        print(f"✅ Final result: {len(final_entries)} vocabulary entries")
        
        state["vocab_entries"] = final_entries
        return state
        
    except Exception as e:
        print(f"❌ Generation error: {e}")
        state["vocab_entries"] = []
        return state

# =========== LangGraph Workflow ===========

def create_vocab_graph() -> StateGraph:
    """Create the vocabulary generation graph with search integration"""
    
    # Create the graph
    workflow = StateGraph(State)
    
    # Add nodes
    workflow.add_node("search", search_node)
    workflow.add_node("generate", generation_node)
    
    # Add edges
    workflow.add_edge(START, "search")
    workflow.add_edge("search", "generate")
    workflow.add_edge("generate", END)
    
    # Compile the graph
    return workflow.compile()

# Create the compiled graph
vocab_graph = create_vocab_graph()

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
    topic_list_name: str = None,
):
    """
    Generate vocabulary for a single topic using LangGraph workflow
    """
    print(f"🚀 Starting LangGraph workflow for topic: {topic}")
    print(f"🔧 Parameters: level={level.value}")
    
    # Create initial state
    initial_state = {
        "topic": topic,
        "level": level,
        "target_language": language_to_learn,
        "original_langauge": learners_native_language,
        "vocab_list": [],
        "vocab_entries": [],
        "vocab_per_batch": vocab_per_batch,
        "phrasal_verbs_per_batch": phrasal_verbs_per_batch,
        "idioms_per_batch": idioms_per_batch
    }
    
    print(f"🔧 Initial state: {initial_state}")
    print(f"🔧 Graph type: {type(vocab_graph)}")
    
    # Run the graph
    try:
        import time
        workflow_start = time.time()
        
        print(f"🚀 Invoking LangGraph workflow...")
        final_state = vocab_graph.invoke(initial_state)
        
        workflow_time = time.time() - workflow_start
        print(f"⏱️ LangGraph workflow completed in {workflow_time:.2f} seconds")
        
        print(f"🔧 Final state keys: {list(final_state.keys()) if final_state else 'None'}")
        print(f"🔧 Vocab entries count: {len(final_state.get('vocab_entries', []))}")
        
        # Return vocabulary entries
        return final_state.get("vocab_entries", [])
        
    except Exception as e:
        print(f"❌ LangGraph workflow error: {e}")
        import traceback
        traceback.print_exc()
        return []
