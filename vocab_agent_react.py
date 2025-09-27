from models import VocabEntry, CEFRLevel, VocabGenerationResponse, PartOfSpeech
from topics import get_topic_list, get_categories, get_topics_by_category
from typing_extensions import TypedDict
from typing import List, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from supabase_database import SupabaseVocabDatabase
from config import Config
from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
import os
import operator

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
    temperature=Config.TOPIC_FOCUS_TEMPERATURE,
    request_timeout=60,
    api_key=Config.OPENAI_API_KEY
)

# =========== Database ===========
db = SupabaseVocabDatabase()

# =========== Custom State for React Agent ===========
class VocabState(TypedDict):
    # Core vocabulary generation parameters
    topic: str
    level: CEFRLevel
    target_language: str
    original_langauge: str
    vocab_per_batch: int
    phrasal_verbs_per_batch: int
    idioms_per_batch: int
    
    # Generation results
    vocab_entries: List[VocabEntry]
    filtered_entries: List[VocabEntry]
    
    # Validation and tracking
    validation_results: List[dict]
    generation_attempts: int
    max_attempts: int
    
    # Regeneration control
    should_regenerate: bool
    regeneration_count: int
    max_regenerations: int
    
    # User preferences
    user_id: str
    ai_role: str
    
    # Messages for react agent
    messages: Annotated[List, operator.add]
    
    # Required for react agent
    remaining_steps: int

# =========== Tools for React Agent ===========

@tool
def filter_duplicates_tool(generated_entries: List[dict], topic: str, target_counts: dict, user_id: str = None, lookback_days: int = 5) -> dict:
    """Filter out duplicate vocabulary entries and determine if regeneration is needed"""
    try:
        print(f"🔍 FILTER_DUPLICATES_TOOL: Starting duplicate filtering")
        print(f"📊 Input: {len(generated_entries)} generated entries for topic: {topic}")
        print(f"🎯 Target counts: {target_counts}")
        print(f"👤 User ID: {user_id}, Lookback: {lookback_days} days")
        
        # Step 1: Get user's saved vocabulary from user_vocab_entries table
        user_saved_words = set()
        if user_id:
            try:
                from supabase_database import SupabaseVocabDatabase
                db = SupabaseVocabDatabase()
                
                # Get user's saved vocabulary entries
                user_saved_entries = db.get_user_saved_vocab_entries(user_id, show_hidden=False)
                print(f"🔍 Found {len(user_saved_entries)} saved vocabulary entries for user")
                
                # Extract words from saved entries
                for entry in user_saved_entries:
                    word = entry.get('word', '').lower().strip()
                    if word:
                        user_saved_words.add(word)
                
                print(f"🔍 Built user saved words set: {len(user_saved_words)} unique words")
                
            except Exception as e:
                print(f"⚠️ Error getting user saved vocabulary: {e}")
                print("Continuing without user saved vocabulary filtering")
        else:
            print("🔍 No user_id provided, skipping user saved vocabulary filtering")
        
        # Step 2: Filter out user-saved duplicates
        saved_filtered_entries = []
        saved_duplicates_found = []
        for entry in generated_entries:
            word = entry.get('word', '').lower().strip()
            
            if word not in user_saved_words:
                saved_filtered_entries.append(entry)
            else:
                saved_duplicates_found.append(word)
        
        print(f"🚫 User-saved duplicates found: {len(saved_duplicates_found)}")
        if saved_duplicates_found:
            print(f"   Saved Duplicates: {', '.join(saved_duplicates_found[:5])}{'...' if len(saved_duplicates_found) > 5 else ''}")
        
        # Step 3: Filter out user-seen duplicates (if user_id provided)
        final_filtered_entries = saved_filtered_entries
        user_duplicates_found = []
        
        if user_id:
            print(f"👤 Checking user generation history for user: {user_id}")
            try:
                from vocab_api import get_user_seen_vocabularies
                seen_words = get_user_seen_vocabularies(user_id, lookback_days)
                print(f"👤 Found {len(seen_words)} words seen by user in last {lookback_days} days")
                
                if seen_words:
                    user_filtered_entries = []
                    for entry in saved_filtered_entries:
                        word = entry.get('word', '').lower().strip()
                        if word not in seen_words:
                            user_filtered_entries.append(entry)
                        else:
                            user_duplicates_found.append(word)
                    
                    final_filtered_entries = user_filtered_entries
                    print(f"🚫 User-seen duplicates found: {len(user_duplicates_found)}")
                    if user_duplicates_found:
                        print(f"   User Duplicates: {', '.join(user_duplicates_found[:5])}{'...' if len(user_duplicates_found) > 5 else ''}")
                
            except Exception as e:
                print(f"⚠️ Error checking user generation history: {e}")
                print("Continuing with saved-filtered entries only")
        
        # Count by type
        vocab_count = len([e for e in final_filtered_entries if e.get('part_of_speech', '').lower() not in ['phrasal_verb', 'idiom']])
        phrasal_count = len([e for e in final_filtered_entries if e.get('part_of_speech', '').lower() == 'phrasal_verb'])
        idiom_count = len([e for e in final_filtered_entries if e.get('part_of_speech', '').lower() == 'idiom'])
        
        print(f"📊 Final filtered counts: {vocab_count} vocab, {phrasal_count} phrasal, {idiom_count} idioms")
        
        # Check if we have enough entries
        target_vocab = target_counts.get('vocab_count', 0)
        target_phrasal = target_counts.get('phrasal_verbs_count', 0)
        target_idiom = target_counts.get('idioms_count', 0)
        
        has_enough = (
            vocab_count >= target_vocab and
            phrasal_count >= target_phrasal and
            idiom_count >= target_idiom
        )
        
        action = "stop" if has_enough else "regenerate"
        print(f"✅ Decision: {action.upper()} - Has enough: {has_enough}")
        print(f"   Need: {target_vocab} vocab, {target_phrasal} phrasal, {target_idiom} idioms")
        print(f"   Have: {vocab_count} vocab, {phrasal_count} phrasal, {idiom_count} idioms")
        
        total_duplicates_removed = len(generated_entries) - len(final_filtered_entries)
        print(f"📊 Total duplicates removed: {total_duplicates_removed} (Saved: {len(saved_duplicates_found)}, User-seen: {len(user_duplicates_found)})")
        
        return {
            "filtered_entries": final_filtered_entries,
            "counts": {
                "vocabularies": vocab_count,
                "phrasal_verbs": phrasal_count,
                "idioms": idiom_count
            },
            "target_counts": target_counts,
            "has_enough": has_enough,
            "duplicates_removed": total_duplicates_removed,
            "saved_duplicates_removed": len(saved_duplicates_found),
            "user_duplicates_removed": len(user_duplicates_found),
            "action": action
        }
        
    except Exception as e:
        print(f"❌ FILTER_DUPLICATES_TOOL ERROR: {str(e)}")
        return {
            "error": f"Filtering failed: {str(e)}",
            "action": "regenerate"
        }

@tool
def generate_vocabulary_tool(topic: str, level: str, target_language: str, original_language: str, 
                           vocab_count: int = 10, phrasal_verbs_count: int = 0, idioms_count: int = 0) -> List[VocabEntry]:
    """Generate vocabulary entries for a given topic and level"""
    try:
        print(f"🎯 GENERATE_VOCABULARY_TOOL: Starting generation")
        print(f"📝 Topic: {topic}, Level: {level}")
        print(f"🌍 Languages: {target_language} -> {original_language}")
        print(f"📊 Target counts: {vocab_count} vocab, {phrasal_verbs_count} phrasal, {idioms_count} idioms")
        
        # Apply 1.5x multiplier with buffer for post-processing
        buffer_vocab = max(int(vocab_count * 1.5), vocab_count + 5)  # At least 1.5x or +5 buffer
        buffer_phrasal = max(int(phrasal_verbs_count * 1.5), phrasal_verbs_count + 3) if phrasal_verbs_count > 0 else 0
        buffer_idioms = max(int(idioms_count * 1.5), idioms_count + 3) if idioms_count > 0 else 0
        
        print(f"📊 Buffer counts: {buffer_vocab} vocab, {buffer_phrasal} phrasal, {buffer_idioms} idioms")
        
        from pydantic import BaseModel, Field
        
        # Define structured output with simpler schema
        class VocabEntryData(BaseModel):
            word: str = Field(description="The vocabulary word")
            definition: str = Field(description="Definition of the word")
            example: str = Field(description="Example sentence")
            translation: str = Field(description="Translation to original language")
            example_translation: str = Field(description="Translation of the example sentence")
            part_of_speech: str = Field(description="Part of speech (noun, verb, adjective, etc.)")
        
        class VocabResponse(BaseModel):
            vocabularies: List[VocabEntryData] = Field(description="List of vocabulary entries")
            phrasal_verbs: List[VocabEntryData] = Field(description="List of phrasal verbs")
            idioms: List[VocabEntryData] = Field(description="List of idioms")
        
        # Create structured LLM using function calling method
        structured_llm = llm.with_structured_output(VocabResponse, method="function_calling")
        
        # Enhanced prompt with strict count requirements and buffer
        prompt = f'''Generate {target_language} vocabulary for "{topic}" at {level} level.

CRITICAL REQUIREMENT - READ THIS FIRST:
You MUST generate EXACTLY {buffer_vocab} vocabulary words. Not {buffer_vocab-1}, not {buffer_vocab+1}, but EXACTLY {buffer_vocab}.

COUNT YOUR RESULTS:
Before responding, count your vocabulary words. If you don't have exactly {buffer_vocab}, add more words or remove some.

STRICT COUNT REQUIREMENTS:
- Generate EXACTLY {buffer_vocab} vocabulary words (nouns, verbs, adjectives, adverbs)
- Generate EXACTLY {buffer_phrasal} phrasal verbs/expressions
- Generate EXACTLY {buffer_idioms} idioms/proverbs

QUALITY REQUIREMENTS:
- All words must be directly relevant to "{topic}"
- Ensure appropriate difficulty for {level} level
- Generate diverse, engaging, and useful vocabulary
- Avoid repetition and generic terms
- Include clear, detailed definitions
- Provide realistic example sentences
- Ensure accurate translations

VALIDATION CHECK:
Before you respond, count your vocabulary words. You should have exactly {buffer_vocab} words.
If you have fewer than {buffer_vocab}, add more words.
If you have more than {buffer_vocab}, remove some words.

For each entry, include:
- word: the vocabulary word
- definition: clear definition in {target_language}
- example: practical example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: part of speech (noun, verb, adjective, adverb, etc.)

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
        
        # Generate with count validation and retry logic
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"🔄 GENERATE_VOCABULARY_TOOL: Attempt {attempt}/{max_attempts}")
            
            result = structured_llm.invoke(prompt)
            
            # Validate counts against buffer requirements
            actual_vocab_count = len(result.vocabularies)
            actual_phrasal_count = len(result.phrasal_verbs)
            actual_idiom_count = len(result.idioms)
            
            print(f"📊 GENERATE_VOCABULARY_TOOL: Generated counts:")
            print(f"   Vocabularies: {actual_vocab_count}/{buffer_vocab} (target: {vocab_count})")
            print(f"   Phrasal verbs: {actual_phrasal_count}/{buffer_phrasal} (target: {phrasal_verbs_count})")
            print(f"   Idioms: {actual_idiom_count}/{buffer_idioms} (target: {idioms_count})")
            
            # Check if counts match buffer requirements
            counts_match = (
                actual_vocab_count == buffer_vocab and
                actual_phrasal_count == buffer_phrasal and
                actual_idiom_count == buffer_idioms
            )
            
            if counts_match:
                print("✅ GENERATE_VOCABULARY_TOOL: All counts match buffer requirements!")
                break
            else:
                print(f"⚠️ GENERATE_VOCABULARY_TOOL: Count mismatch detected. Attempt {attempt}/{max_attempts}")
                if attempt < max_attempts:
                    # Add specific retry instruction for buffer counts
                    prompt += f"\n\nRETRY INSTRUCTION: Previous attempt generated {actual_vocab_count} vocabularies, {actual_phrasal_count} phrasal verbs, and {actual_idiom_count} idioms. You need exactly {buffer_vocab} vocabularies, {buffer_phrasal} phrasal verbs, and {buffer_idioms} idioms. Please count carefully and generate the exact numbers requested."
                    print(f"🔄 GENERATE_VOCABULARY_TOOL: Added retry instruction to prompt")
                else:
                    print("❌ GENERATE_VOCABULARY_TOOL: Max attempts reached. Using generated results as-is.")
        
        # Convert to VocabEntry objects with post-processing to exact counts
        vocab_entries = []
        
        # Process vocabularies (trim to exact count)
        vocab_list = result.vocabularies[:vocab_count]  # Take only the requested number
        for vocab in vocab_list:
            entry = VocabEntry(
                word=vocab.word,
                definition=vocab.definition,
                example=vocab.example,
                translation=vocab.translation,
                example_translation=vocab.example_translation,
                part_of_speech=PartOfSpeech(vocab.part_of_speech),
                level=CEFRLevel(level)
            )
            vocab_entries.append(entry)
        
        # Process phrasal verbs (trim to exact count)
        phrasal_list = result.phrasal_verbs[:phrasal_verbs_count]  # Take only the requested number
        for pv in phrasal_list:
            entry = VocabEntry(
                word=pv.word,
                definition=pv.definition,
                example=pv.example,
                translation=pv.translation,
                example_translation=pv.example_translation,
                part_of_speech=PartOfSpeech('phrasal_verb'),
                level=CEFRLevel(level)
            )
            vocab_entries.append(entry)
        
        # Process idioms (trim to exact count)
        idiom_list = result.idioms[:idioms_count]  # Take only the requested number
        for idiom in idiom_list:
            entry = VocabEntry(
                word=idiom.word,
                definition=idiom.definition,
                example=idiom.example,
                translation=idiom.translation,
                example_translation=idiom.example_translation,
                part_of_speech=PartOfSpeech('idiom'),
                level=CEFRLevel(level)
            )
            vocab_entries.append(entry)
        
        print(f"✅ GENERATE_VOCABULARY_TOOL: Final result: {len(vocab_entries)} vocabulary entries")
        print(f"🔍 GENERATE_VOCABULARY_TOOL: Post-processed counts - Vocabularies: {len(vocab_list)}, Phrasal verbs: {len(phrasal_list)}, Idioms: {len(idiom_list)}")
        print(f"📊 GENERATE_VOCABULARY_TOOL: Original counts - Vocabularies: {len(result.vocabularies)}, Phrasal verbs: {len(result.phrasal_verbs)}, Idioms: {len(result.idioms)}")
        
        return vocab_entries
        
    except Exception as e:
        print(f"❌ GENERATE_VOCABULARY_TOOL ERROR: {str(e)}")
        return []

@tool
def search_topic_context(topic: str, level: str = None, language: str = "English") -> str:
    """Search for additional context about a topic"""
    try:
        # Initialize Tavily search
        tavily = TavilySearch(api_key=Config.TAVILY_API_KEY)
        
        # Create search query
        search_query = f"{topic} vocabulary {level} level {language} language learning"
        
        # Perform search
        results = tavily.invoke(search_query)
        
        if results and len(results) > 0:
            # Extract relevant context
            context = ""
            for result in results[:3]:  # Use top 3 results
                if 'content' in result:
                    context += result['content'][:500] + "\n\n"
            
            return f"Found context for {topic}: {context[:1000]}..."
        else:
            return f"No additional context found for {topic}"
            
    except Exception as e:
        return f"Search error: {str(e)}"

# =========== React Agent Creation ===========

def create_vocab_react_agent():
    """Create a react agent for vocabulary generation"""
    
    # Define tools
    tools = [
        generate_vocabulary_tool,
        filter_duplicates_tool,
        search_topic_context
    ]
    
    # Create react agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_schema=VocabState
    )
    
    return agent

def create_vocab_graph_with_regeneration():
    """Create a LangGraph with regeneration loop for vocabulary generation"""
    
    # Create the graph
    workflow = StateGraph(VocabState)
    
    # Add nodes
    workflow.add_node("generate", generate_vocabulary_node)
    workflow.add_node("filter", filter_duplicates_node)
    workflow.add_node("decide", decide_regeneration_node)
    
    # Add edges
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "filter")
    workflow.add_edge("filter", "decide")
    
    # Add conditional edges for regeneration loop
    workflow.add_conditional_edges(
        "decide",
        should_continue_generation,
        {
            "regenerate": "generate",
            "stop": END
        }
    )
    
    # Compile the graph
    return workflow.compile()

def generate_vocabulary_node(state: VocabState) -> VocabState:
    """Generate vocabulary entries"""
    print(f"🎯 GENERATION_NODE: Starting generation (attempt {state.get('regeneration_count', 0) + 1})")
    
    # Use the generate_vocabulary_tool
    vocab_result = generate_vocabulary_tool.invoke({
        "topic": state["topic"],
        "level": state["level"].value,
        "target_language": state["target_language"],
        "original_language": state["original_langauge"],
        "vocab_count": state["vocab_per_batch"],
        "phrasal_verbs_count": state["phrasal_verbs_per_batch"],
        "idioms_count": state["idioms_per_batch"]
    })
    
    # Update state with generated entries
    state["vocab_entries"] = vocab_result
    state["regeneration_count"] = state.get("regeneration_count", 0) + 1
    
    print(f"✅ GENERATION_NODE: Generated {len(vocab_result)} entries")
    return state

def filter_duplicates_node(state: VocabState) -> VocabState:
    """Filter duplicates and validate counts"""
    print(f"🔍 FILTER_NODE: Starting duplicate filtering")
    
    # Convert VocabEntry objects to dict format for filtering
    generated_entries = []
    for entry in state["vocab_entries"]:
        generated_entries.append({
            'word': entry.word,
            'definition': entry.definition,
            'example': entry.example,
            'translation': entry.translation,
            'example_translation': entry.example_translation,
            'part_of_speech': entry.part_of_speech.value if entry.part_of_speech else '',
            'level': entry.level.value if entry.level else ''
        })
    
    # Use filter_duplicates_tool
    filter_result = filter_duplicates_tool.invoke({
        "generated_entries": generated_entries,
        "topic": state["topic"],
        "target_counts": {
            "vocab_count": state["vocab_per_batch"],
            "phrasal_verbs_count": state["phrasal_verbs_per_batch"],
            "idioms_count": state["idioms_per_batch"]
        },
        "user_id": state["user_id"],
        "lookback_days": 5
    })
    
    # Convert filtered entries back to VocabEntry objects
    filtered_entries = filter_result.get("filtered_entries", [])
    vocab_entries = []
    for entry_dict in filtered_entries:
        entry = VocabEntry(
            word=entry_dict['word'],
            definition=entry_dict['definition'],
            example=entry_dict['example'],
            translation=entry_dict['translation'],
            example_translation=entry_dict['example_translation'],
            part_of_speech=PartOfSpeech(entry_dict['part_of_speech']),
            level=CEFRLevel(entry_dict['level'])
        )
        vocab_entries.append(entry)
    
    # Update state
    state["filtered_entries"] = vocab_entries
    state["validation_results"] = [filter_result]
    
    print(f"✅ FILTER_NODE: Filtered to {len(vocab_entries)} entries")
    return state

def decide_regeneration_node(state: VocabState) -> VocabState:
    """Decide whether to regenerate or stop"""
    print(f"🤔 DECIDE_NODE: Evaluating regeneration decision")
    
    filter_result = state["validation_results"][-1]
    has_enough = filter_result.get("has_enough", False)
    max_regenerations = state.get("max_regenerations", 3)
    regeneration_count = state.get("regeneration_count", 0)
    
    # Decide based on count and regeneration limit
    if has_enough:
        state["should_regenerate"] = False
        print(f"✅ DECIDE_NODE: Has enough entries, stopping")
    elif regeneration_count >= max_regenerations:
        state["should_regenerate"] = False
        print(f"⚠️ DECIDE_NODE: Max regenerations reached ({max_regenerations}), stopping")
    else:
        state["should_regenerate"] = True
        print(f"🔄 DECIDE_NODE: Need more entries, will regenerate")
    
    return state

def should_continue_generation(state: VocabState) -> str:
    """Route function for conditional edges"""
    if state.get("should_regenerate", False):
        return "regenerate"
    else:
        return "stop"

# =========== Main Generation Function ===========

def generate_vocab_with_regeneration_loop(
    topic: str,
    level: CEFRLevel,
    target_language: str = "English",
    original_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 0,
    idioms_per_batch: int = 0,
    user_id: str = "default_user",
    ai_role: str = "Language Teacher",
    max_regenerations: int = 3
) -> VocabGenerationResponse:
    """
    Generate vocabulary using LangGraph with regeneration loop
    """
    try:
        print(f"🚀 Starting vocabulary generation with regeneration loop for '{topic}'")
        
        # Create the graph
        graph = create_vocab_graph_with_regeneration()
        
        # Create initial state
        initial_state = {
            "topic": topic,
            "level": level,
            "target_language": target_language,
            "original_langauge": original_language,
            "vocab_per_batch": vocab_per_batch,
            "phrasal_verbs_per_batch": phrasal_verbs_per_batch,
            "idioms_per_batch": idioms_per_batch,
            "vocab_entries": [],
            "filtered_entries": [],
            "validation_results": [],
            "generation_attempts": 0,
            "max_attempts": 3,
            "should_regenerate": True,
            "regeneration_count": 0,
            "max_regenerations": max_regenerations,
            "user_id": user_id,
            "ai_role": ai_role,
            "messages": [],
            "remaining_steps": 10
        }
        
        # Run the graph
        final_state = graph.invoke(initial_state)
        
        # Extract final results
        final_entries = final_state.get("filtered_entries", [])
        
        # Separate entries by type
        vocabularies = [entry for entry in final_entries if entry.part_of_speech != PartOfSpeech.PHRASAL_VERB and entry.part_of_speech != PartOfSpeech.IDIOM]
        phrasal_verbs = [entry for entry in final_entries if entry.part_of_speech == PartOfSpeech.PHRASAL_VERB]
        idioms = [entry for entry in final_entries if entry.part_of_speech == PartOfSpeech.IDIOM]
        
        print(f"✅ Final result: {len(vocabularies)} vocab, {len(phrasal_verbs)} phrasal, {len(idioms)} idioms")
        print(f"🔄 Total regenerations: {final_state.get('regeneration_count', 0)}")
        
        # Final summary statistics (like vocab_agent.py does)
        print(f"\n📊 FINAL SUMMARY:")
        print(f"Topic: {topic}")
        print(f"Level: {level.value}")
        print(f"Target language: {target_language}")
        print(f"Original language: {original_language}")
        print(f"Total entries created: {len(final_entries)}")
        print(f"Regenerations used: {final_state.get('regeneration_count', 0)}")
        print(f"User ID: {user_id}")
        print("✅ Generation completed successfully!")
        
        # Save generated vocabularies to database (like vocab_agent.py does)
        if final_entries:
            print(f"\n💾 Saving {len(final_entries)} new entries to database...")
            try:
                from supabase_database import SupabaseVocabDatabase
                db = SupabaseVocabDatabase()
                
                # Save to vocab_entries table
                db.insert_vocab_entries(
                    entries=final_entries,
                    topic_name=topic,
                    category_name="general",  # Default category
                    target_language=target_language,
                    original_language=original_language
                )
                print("✅ Saved successfully to vocab_entries table!")
                
                # Verify the count after saving (like vocab_agent.py does)
                try:
                    saved_entries = db.get_vocab_entries(topic_name=topic, category_name="general")
                    print(f"📊 Total entries in database for '{topic}': {len(saved_entries)}")
                except Exception as e:
                    print(f"⚠️ Error verifying saved entries count: {e}")
                
            except Exception as e:
                print(f"⚠️ Error saving to vocab_entries: {e}")
        
        # Track generated vocabularies for user (like vocab_api.py does)
        if user_id and final_entries:
            print(f"📊 Tracking {len(final_entries)} generated vocabularies for user...")
            try:
                from vocab_api import track_generated_vocabularies
                import uuid
                
                session_id = str(uuid.uuid4())
                track_generated_vocabularies(user_id, final_entries, topic, level, session_id)
                print("✅ Tracked successfully in user_generation_history!")
                
            except Exception as e:
                print(f"⚠️ Error tracking generation history: {e}")
        
        # Create response with statistics (like vocab_agent.py does)
        response = VocabGenerationResponse(
            vocabularies=vocabularies,
            phrasal_verbs=phrasal_verbs,
            idioms=idioms
        )
        
        # Print statistics (since we can't extend the Pydantic model)
        print(f"\n📊 RESPONSE STATISTICS:")
        print(f"   Total entries created: {len(final_entries)}")
        print(f"   Regenerations used: {final_state.get('regeneration_count', 0)}")
        print(f"   Topic: {topic}")
        print(f"   Level: {level.value}")
        print(f"   User ID: {user_id}")
        
        return response
        
    except Exception as e:
        print(f"❌ Regeneration loop error: {e}")
        return VocabGenerationResponse(
            vocabularies=[],
            phrasal_verbs=[],
            idioms=[]
        )

def generate_vocab_with_react_agent(
    topic: str,
    level: CEFRLevel,
    target_language: str = "English",
    original_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 0,
    idioms_per_batch: int = 0,
    user_id: str = "default_user",
    ai_role: str = "Language Teacher"
) -> VocabGenerationResponse:
    """
    Generate vocabulary using react agent approach
    """
    try:
        print(f"🚀 Starting react agent vocabulary generation for '{topic}'")
        
        # Use the generate_vocabulary_tool directly - it already has all the logic we need
        vocab_result = generate_vocabulary_tool.invoke({
            "topic": topic,
            "level": level.value,
            "target_language": target_language,
            "original_language": original_language,
            "vocab_count": vocab_per_batch,
            "phrasal_verbs_count": phrasal_verbs_per_batch,
            "idioms_count": idioms_per_batch
        })
        
        print(f"📊 Tool result: {len(vocab_result)} vocabulary entries")
        
        # Convert VocabEntry objects to dict format for filtering
        generated_entries = []
        for entry in vocab_result:
            generated_entries.append({
                'word': entry.word,
                'definition': entry.definition,
                'example': entry.example,
                'translation': entry.translation,
                'example_translation': entry.example_translation,
                'part_of_speech': entry.part_of_speech.value if entry.part_of_speech else '',
                'level': entry.level.value if entry.level else ''
            })
        
        # Use filter_duplicates_tool to filter out duplicates
        filter_result = filter_duplicates_tool.invoke({
            "generated_entries": generated_entries,
            "topic": topic,
            "target_counts": {
                "vocab_count": vocab_per_batch,
                "phrasal_verbs_count": phrasal_verbs_per_batch,
                "idioms_count": idioms_per_batch
            },
            "user_id": user_id,
            "lookback_days": 5
        })
        
        print(f"🔍 Filter result: {filter_result}")
        
        # Convert filtered entries back to VocabEntry objects
        filtered_entries = filter_result.get("filtered_entries", [])
        vocab_entries = []
        for entry_dict in filtered_entries:
            entry = VocabEntry(
                word=entry_dict['word'],
                definition=entry_dict['definition'],
                example=entry_dict['example'],
                translation=entry_dict['translation'],
                example_translation=entry_dict['example_translation'],
                part_of_speech=PartOfSpeech(entry_dict['part_of_speech']),
                level=CEFRLevel(entry_dict['level'])
            )
            vocab_entries.append(entry)
        
        print(f"✅ Generated {len(vocab_entries)} actual vocabulary entries after filtering")
        
        # Separate entries by type
        vocabularies = [entry for entry in vocab_entries if entry.part_of_speech != PartOfSpeech.PHRASAL_VERB and entry.part_of_speech != PartOfSpeech.IDIOM]
        phrasal_verbs = [entry for entry in vocab_entries if entry.part_of_speech == PartOfSpeech.PHRASAL_VERB]
        idioms = [entry for entry in vocab_entries if entry.part_of_speech == PartOfSpeech.IDIOM]
        
        # Create response
        response = VocabGenerationResponse(
            vocabularies=vocabularies,
            phrasal_verbs=phrasal_verbs,
            idioms=idioms
        )
        
        return response
        
    except Exception as e:
        print(f"❌ React agent error: {e}")
        return VocabGenerationResponse(
            vocabularies=[],
            phrasal_verbs=[],
            idioms=[]
        )

# =========== Legacy Compatibility ===========

def generate_vocab(
    topic: str,
    level: CEFRLevel,
    target_language: str = "English",
    original_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 0,
    idioms_per_batch: int = 0,
    user_id: str = "default_user",
    ai_role: str = "Language Teacher"
) -> VocabGenerationResponse:
    """
    Legacy function that uses react agent approach
    """
    return generate_vocab_with_react_agent(
        topic=topic,
        level=level,
        target_language=target_language,
        original_language=original_language,
        vocab_per_batch=vocab_per_batch,
        phrasal_verbs_per_batch=phrasal_verbs_per_batch,
        idioms_per_batch=idioms_per_batch,
        user_id=user_id,
        ai_role=ai_role
    )
