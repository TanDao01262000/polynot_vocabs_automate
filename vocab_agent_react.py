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
import random

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
def filter_duplicates_tool(generated_entries: List[dict], topic: str, target_counts: dict, user_id: str = None, lookback_days: int = 2) -> dict:
    """
    Filter out duplicate vocabulary entries and determine if regeneration is needed.
    
    This tool performs two-step filtering:
    1. Filters out vocabulary that the user has already saved to their personal list
    2. Filters out vocabulary that the user has recently seen (within lookback_days)
    
    It preserves the type distribution (vocab, phrasal_verbs, idioms) and returns
    a decision on whether to regenerate if not enough entries remain.
    
    Args:
        generated_entries: List of generated vocabulary entries as dictionaries
        topic: The topic being generated for
        target_counts: Dict with 'vocab_count', 'phrasal_verbs_count', 'idioms_count'
        user_id: User ID for filtering against saved/seen vocabulary
        lookback_days: Number of days to look back for user-seen vocabulary
    
    Returns:
        Dict with:
        - filtered_entries: List of entries after filtering
        - counts: Dict with actual counts by type
        - has_enough: Boolean indicating if target counts are met
        - action: "stop" or "regenerate"
        - duplicates_removed: Total number of duplicates removed
        
    Note:
        This tool is used by the LangGraph workflow to decide whether to
        continue generating or stop the regeneration loop.
    """
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
        
        # Step 3: Filter out user-seen duplicates (if user_id provided) - PRESERVE TYPE DISTRIBUTION
        final_filtered_entries = saved_filtered_entries
        user_duplicates_found = []
        
        if user_id:
            print(f"👤 Checking user generation history for user: {user_id}")
            try:
                from vocab_api import get_user_seen_vocabularies
                
                # Function now uses service role client internally (reduced lookback from 5 to 2 days)
                seen_words = get_user_seen_vocabularies(user_id, 2)
                print(f"👤 Found {len(seen_words)} words seen by user in last 2 days")
                
                if seen_words:
                    # Filter by type to preserve distribution
                    user_filtered_vocab = []
                    user_filtered_phrasal = []
                    user_filtered_idioms = []
                    
                    for entry in saved_filtered_entries:
                        word = entry.get('word', '').lower().strip()
                        part_of_speech = entry.get('part_of_speech', '').lower()
                        
                        if word not in seen_words:
                            if part_of_speech == 'phrasal_verb':
                                user_filtered_phrasal.append(entry)
                            elif part_of_speech == 'idiom':
                                user_filtered_idioms.append(entry)
                            else:
                                user_filtered_vocab.append(entry)
                        else:
                            user_duplicates_found.append(word)
                    
                    # Reconstruct final entries maintaining type order
                    final_filtered_entries = user_filtered_vocab + user_filtered_phrasal + user_filtered_idioms
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
    """
    Generate vocabulary entries for a given topic and level.
    
    This tool generates vocabulary words, phrasal verbs, and idioms related to the specified topic.
    It uses a simple prompt and relies on the LangGraph conditional edges to handle retry logic
    if the generated counts don't meet the target requirements.
    
    Args:
        topic: The topic to generate vocabulary for
        level: The CEFR level (A1, A2, B1, B2, C1, C2)
        target_language: The language to learn (e.g., "English")
        original_language: The learner's native language (e.g., "Vietnamese")
        vocab_count: Number of vocabulary words to generate
        phrasal_verbs_count: Number of phrasal verbs to generate
        idioms_count: Number of idioms to generate
    
    Returns:
        List of VocabEntry objects with word, definition, example, translation, etc.
        
    Note:
        This tool generates once and returns the result. The LangGraph workflow
        will handle retries if the counts don't meet requirements.
    """
    try:
        print(f"🎯 GENERATE_VOCABULARY_TOOL: Starting generation")
        print(f"📝 Topic: {topic}, Level: {level}")
        print(f"🌍 Languages: {target_language} -> {original_language}")
        print(f"📊 Target counts: {vocab_count} vocab, {phrasal_verbs_count} phrasal, {idioms_count} idioms")
        
        # Apply 1.5x multiplier with buffer for post-processing
        buffer_vocab = max(int(vocab_count * 1.5), vocab_count + 3)  # Reduced to 1.5x
        buffer_phrasal = max(int(phrasal_verbs_count * 1.5), phrasal_verbs_count + 2) if phrasal_verbs_count > 0 else 0
        buffer_idioms = max(int(idioms_count * 1.5), idioms_count + 2) if idioms_count > 0 else 0
        
        print(f"📊 Buffer counts: {buffer_vocab} vocab, {buffer_phrasal} phrasal, {buffer_idioms} idioms")
        
        from pydantic import BaseModel, Field
        
        # Define structured output without strict validation
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
        
        # Use the main LLM with slightly higher temperature for diversity
        try:
            gen_temperature = float(os.getenv("VOCAB_GEN_TEMPERATURE", "0.7"))
        except Exception:
            gen_temperature = 0.7
        
        # Create structured LLM using function calling method with more conservative settings
        structured_llm = llm.with_structured_output(VocabResponse, method="function_calling")
        
        # Optionally fetch brief search context to broaden variety (kept short to avoid prompt bloat)
        search_context_text = ""
        try:
            print(f"🔎 GENERATE_SEARCH: Starting search for topic: {topic}")
            tavily = TavilySearch(api_key=Config.TAVILY_API_KEY)
            # Level-specific query options for appropriate vocabulary
            level_queries = {
                "A1": [
                    f"{topic} basic vocabulary {level}",
                    f"{topic} simple words {level}",
                    f"{topic} beginner vocabulary {level}",
                    f"{topic} essential words {level}",
                    f"{topic} common vocabulary {level}"
                ],
                "A2": [
                    f"{topic} vocabulary {level} level",
                    f"{topic} everyday words {level}",
                    f"{topic} practical vocabulary {level}",
                    f"{topic} useful words {level}",
                    f"{topic} common terms {level}"
                ],
                "B1": [
                    f"{topic} vocabulary {level} level",
                    f"{topic} intermediate vocabulary {level}",
                    f"{topic} practical terms {level}",
                    f"{topic} business vocabulary {level}",
                    f"{topic} professional words {level}"
                ],
                "B2": [
                    f"{topic} vocabulary {level} level",
                    f"{topic} advanced vocabulary {level}",
                    f"{topic} professional terms {level}",
                    f"{topic} business language {level}",
                    f"{topic} specialized vocabulary {level}"
                ],
                "C1": [
                    f"{topic} vocabulary {level} level",
                    f"{topic} advanced terminology {level}",
                    f"{topic} professional language {level}",
                    f"{topic} expert vocabulary {level}",
                    f"{topic} specialized terms {level}"
                ],
                "C2": [
                    f"{topic} vocabulary {level} level",
                    f"{topic} expert terminology {level}",
                    f"{topic} professional language {level}",
                    f"{topic} specialized vocabulary {level}",
                    f"{topic} industry jargon {level}"
                ]
            }
            
            # Get level-specific queries or fallback to general
            query_options = level_queries.get(level, [
                f"{topic} vocabulary {level} level",
                f"{topic} professional terms {level}",
                f"{topic} business vocabulary {level}",
                f"{topic} specialized vocabulary {level}",
                f"{topic} advanced terminology {level}"
            ])
            # Randomly select 2-3 queries for variety
            num_queries = random.randint(2, 3)
            selected_queries = random.sample(query_options, k=min(num_queries, len(query_options)))
            print(f"🔎 GENERATE_SEARCH: Selected {len(selected_queries)} queries: {selected_queries}")
            snippets: List[str] = []
            for i, q in enumerate(selected_queries):
                try:
                    print(f"🔎 GENERATE_SEARCH: Query {i+1}: {q}")
                    res = tavily.invoke(q)
                    print(f"🔎 GENERATE_SEARCH: Query {i+1} result type: {type(res)}")
                    if not res:
                        print(f"🔎 GENERATE_SEARCH: Query {i+1} returned empty result")
                        continue
                    
                    # Handle different response formats
                    items = []
                    if isinstance(res, dict):
                        items = res.get("results", [])
                        print(f"🔎 GENERATE_SEARCH: Query {i+1} found {len(items)} results in dict")
                    elif isinstance(res, list):
                        items = res
                        print(f"🔎 GENERATE_SEARCH: Query {i+1} found {len(items)} results in list")
                    else:
                        print(f"🔎 GENERATE_SEARCH: Query {i+1} unexpected result format: {type(res)}")
                        continue
                    
                    # Randomly select 1-2 items from results for variety
                    num_items = random.randint(1, 2)
                    selected_items = items[:num_items]
                    print(f"🔎 GENERATE_SEARCH: Processing {len(selected_items)} items from query {i+1}")
                    
                    for j, item in enumerate(selected_items):
                        print(f"🔎 GENERATE_SEARCH: Processing item {j+1} from query {i+1}: {type(item)}")
                        if isinstance(item, dict):
                            content = item.get("content") or item.get("snippet") or item.get("text") or ""
                            print(f"🔎 GENERATE_SEARCH: Item {j+1} content length: {len(content)}")
                            if content:
                                # Random snippet length for variety
                                snippet_length = random.randint(300, 500)
                                snippet = content[:snippet_length]
                                snippets.append(snippet)
                                print(f"🔎 GENERATE_SEARCH: Added snippet {len(snippet)} chars from query {i+1}")
                            else:
                                print(f"🔎 GENERATE_SEARCH: Item {j+1} has no content")
                        else:
                            print(f"🔎 GENERATE_SEARCH: Item {j+1} is not a dict: {item}")
                except Exception as e:
                    print(f"⚠️ GENERATE_SEARCH: Error with query '{q}': {e}")
                    continue
            if snippets:
                search_context_text = "\n".join(snippets)[:800]
                print(f"🔎 GENERATE_SEARCH: Final result: {len(snippets)} snippets ({len(search_context_text)} chars)")
                print(f"🔎 GENERATE_SEARCH: Context preview: {search_context_text[:200]}...")
            else:
                print(f"🔎 GENERATE_SEARCH: No snippets collected")
        except Exception as e:
            print(f"⚠️ GENERATE_SEARCH: Skipped due to error: {e}")
            import traceback
            traceback.print_exc()
        
        # Enhanced prompt with search integration for better quality
        if search_context_text:
            prompt = f'''Generate HIGH-QUALITY {target_language} vocabulary for "{topic}" at {level} level.

SEARCH CONTEXT FOR QUALITY:
{search_context_text}

Based on the search context above, generate PROFESSIONAL and PRACTICAL vocabulary words, phrasal verbs, and idioms related to "{topic}". 
Focus on USEFUL, REAL-WORLD terms that professionals and advanced learners would use.

QUALITY REQUIREMENTS:
- Use terms from the search context when possible
- Focus on PRACTICAL, PROFESSIONAL vocabulary
- Include ADVANCED, SPECIALIZED terminology
- Provide REALISTIC, PROFESSIONAL examples
- Use terms that show EXPERTISE and SOPHISTICATION

For each entry, provide:
- word: the vocabulary word (prefer advanced/professional terms)
- definition: clear, professional definition in {target_language}
- example: realistic, professional example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: one of "noun", "verb", "adjective", "adverb", "phrasal_verb", "idiom"

Return as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
        else:
            prompt = f'''Generate HIGH-QUALITY {target_language} vocabulary for "{topic}" at {level} level.

Generate PROFESSIONAL and PRACTICAL vocabulary words, phrasal verbs, and idioms related to "{topic}".
Focus on USEFUL, REAL-WORLD terms that professionals and advanced learners would use.

QUALITY REQUIREMENTS:
- Focus on PRACTICAL, PROFESSIONAL vocabulary
- Include ADVANCED, SPECIALIZED terminology
- Provide REALISTIC, PROFESSIONAL examples
- Use terms that show EXPERTISE and SOPHISTICATION

For each entry, provide:
- word: the vocabulary word (prefer advanced/professional terms)
- definition: clear, professional definition in {target_language}
- example: realistic, professional example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: one of "noun", "verb", "adjective", "adverb", "phrasal_verb", "idiom"

Return as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
        
        # Generate once - conditional edges will handle retry logic
        print(f"🔄 GENERATE_VOCABULARY_TOOL: Single generation attempt")
        
        try:
            result = structured_llm.invoke(prompt)
            
            # Log generated counts
            actual_vocab_count = len(result.vocabularies)
            actual_phrasal_count = len(result.phrasal_verbs)
            actual_idiom_count = len(result.idioms)
            
            print(f"📊 GENERATE_VOCABULARY_TOOL: Generated counts:")
            print(f"   Vocabularies: {actual_vocab_count} (target: {vocab_count})")
            print(f"   Phrasal verbs: {actual_phrasal_count} (target: {phrasal_verbs_count})")
            print(f"   Idioms: {actual_idiom_count} (target: {idioms_count})")
            
            # Always return result - let conditional edges decide if retry is needed
            print("✅ GENERATE_VOCABULARY_TOOL: Generated result - conditional edges will validate")
            
        except Exception as e:
            print(f"⚠️ GENERATE_VOCABULARY_TOOL: Generation failed - {str(e)}")
            return []
        
        # Convert to VocabEntry objects with post-processing to exact counts
        vocab_entries = []
        
        # Process vocabularies (shuffle, then trim to exact count)
        vocab_list_raw = list(result.vocabularies)
        random.shuffle(vocab_list_raw)
        vocab_list = vocab_list_raw[:vocab_count]
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
        
        # Process phrasal verbs (shuffle, then trim to exact count)
        phrasal_list_raw = list(result.phrasal_verbs)
        random.shuffle(phrasal_list_raw)
        phrasal_list = phrasal_list_raw[:phrasal_verbs_count]
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
        
        # Process idioms (shuffle, then trim to exact count)
        idiom_list_raw = list(result.idioms)
        random.shuffle(idiom_list_raw)
        idiom_list = idiom_list_raw[:idioms_count]
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
    """
    Search for additional context about a topic to enhance vocabulary generation.
    
    This tool uses Tavily search to find relevant information about the topic,
    which can be used to generate more diverse and contextually appropriate vocabulary.
    It searches for advanced vocabulary, specialized terms, and uncommon words
    related to the topic.
    
    Args:
        topic: The topic to search for
        level: Optional CEFR level to include in search
        language: The target language (default: "English")
    
    Returns:
        String containing search results and context about the topic
        
    Note:
        This tool is optional and can be used to provide additional context
        for vocabulary generation, but the generation tool works fine without it.
    """
    try:
        print(f"🔍 SEARCH_TOOL: Starting search for topic: {topic}")
        
        # Initialize Tavily search
        tavily = TavilySearch(api_key=Config.TAVILY_API_KEY)
        
        # Create level-specific search query for appropriate vocabulary
        import random
        level_queries = {
            "A1": [
                f"{topic} basic vocabulary {level} level {language}",
                f"{topic} simple words {level} {language}",
                f"{topic} beginner vocabulary {level} {language}",
                f"{topic} essential words {level} {language}"
            ],
            "A2": [
                f"{topic} vocabulary {level} level {language}",
                f"{topic} everyday words {level} {language}",
                f"{topic} practical vocabulary {level} {language}",
                f"{topic} useful words {level} {language}"
            ],
            "B1": [
                f"{topic} vocabulary {level} level {language}",
                f"{topic} intermediate vocabulary {level} {language}",
                f"{topic} practical terms {level} {language}",
                f"{topic} business vocabulary {level} {language}"
            ],
            "B2": [
                f"{topic} vocabulary {level} level {language}",
                f"{topic} advanced vocabulary {level} {language}",
                f"{topic} professional terms {level} {language}",
                f"{topic} business language {level} {language}"
            ],
            "C1": [
                f"{topic} vocabulary {level} level {language}",
                f"{topic} advanced terminology {level} {language}",
                f"{topic} professional language {level} {language}",
                f"{topic} expert vocabulary {level} {language}"
            ],
            "C2": [
                f"{topic} vocabulary {level} level {language}",
                f"{topic} expert terminology {level} {language}",
                f"{topic} professional language {level} {language}",
                f"{topic} specialized vocabulary {level} {language}"
            ]
        }
        
        # Get level-specific queries or fallback to general
        query_templates = level_queries.get(level, [
            f"{topic} vocabulary {level} level {language}",
            f"{topic} professional terms {level} {language}",
            f"{topic} business vocabulary {level} {language}"
        ])
        search_query = random.choice(query_templates)
        print(f"🔍 SEARCH_TOOL: Selected level-specific query: {search_query}")
        
        # Perform search
        results = tavily.invoke(search_query)
        print(f"🔍 SEARCH_TOOL: Raw results type: {type(results)}")
        print(f"🔍 SEARCH_TOOL: Raw results keys: {list(results.keys()) if isinstance(results, dict) else 'Not a dict'}")
        
        if results and isinstance(results, dict) and 'results' in results:
            search_results = results['results']
            print(f"🔍 SEARCH_TOOL: Found {len(search_results)} search results")
            
            # Extract relevant context from Tavily results
            context = ""
            for i, result in enumerate(search_results[:3]):  # Use top 3 results
                print(f"🔍 SEARCH_TOOL: Processing result {i+1}: {type(result)}")
                if isinstance(result, dict):
                    print(f"🔍 SEARCH_TOOL: Result {i+1} keys: {list(result.keys())}")
                    if 'content' in result:
                        content = result['content']
                        print(f"🔍 SEARCH_TOOL: Result {i+1} content length: {len(content)}")
                        print(f"🔍 SEARCH_TOOL: Result {i+1} content preview: {content[:200]}...")
                        context += content[:500] + "\n\n"
                    else:
                        print(f"🔍 SEARCH_TOOL: Result {i+1} has no 'content' key")
                else:
                    print(f"🔍 SEARCH_TOOL: Result {i+1} is not a dict: {result}")
            
            print(f"🔍 SEARCH_TOOL: Final context length: {len(context)}")
            if context:
                final_result = f"Found context for {topic}: {context[:1000]}..."
                print(f"🔍 SEARCH_TOOL: Returning context (truncated to 1000 chars)")
                return final_result
            else:
                print(f"🔍 SEARCH_TOOL: No content extracted from results")
                return f"No content found in search results for {topic}"
        else:
            print(f"🔍 SEARCH_TOOL: Invalid results format")
            return f"No additional context found for {topic}"
            
    except Exception as e:
        print(f"🔍 SEARCH_TOOL: Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
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
        "lookback_days": 2
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
    """Decide whether to regenerate or stop - with hard limit to prevent infinite loops"""
    print(f"🤔 DECIDE_NODE: Evaluating regeneration decision")
    
    filter_result = state["validation_results"][-1]
    has_enough = filter_result.get("has_enough", False)
    max_regenerations = state.get("max_regenerations", 3)
    regeneration_count = state.get("regeneration_count", 0)
    
    if has_enough:
        state["should_regenerate"] = False
        print(f"✅ DECIDE_NODE: Has enough entries, stopping")
    else:
        # Check if we've exceeded the hard limit
        if regeneration_count >= max_regenerations:
            state["should_regenerate"] = False
            print(f"🛑 DECIDE_NODE: Reached max regenerations ({max_regenerations}), stopping with current results")
            print(f"📊 DECIDE_NODE: Returning {len(state.get('filtered_entries', []))} entries (may be less than requested)")
        else:
            state["should_regenerate"] = True
            print(f"🔄 DECIDE_NODE: Need more entries, will regenerate (attempt {regeneration_count + 1}/{max_regenerations})")
    
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
        
        # Run the graph with reasonable limits to prevent infinite loops
        final_state = graph.invoke(initial_state, config={
            "recursion_limit": 20,  # Reduced from 50 to prevent excessive loops
            "timeout": 120  # 2 minute timeout (reduced from 5 minutes)
        })
        
        # Extract final results
        final_entries = final_state.get("filtered_entries", [])
        
        # Separate entries by type
        vocabularies = [entry for entry in final_entries if entry.part_of_speech != PartOfSpeech.PHRASAL_VERB and entry.part_of_speech != PartOfSpeech.IDIOM]
        phrasal_verbs = [entry for entry in final_entries if entry.part_of_speech == PartOfSpeech.PHRASAL_VERB]
        idioms = [entry for entry in final_entries if entry.part_of_speech == PartOfSpeech.IDIOM]
        
        print(f"✅ Final result: {len(vocabularies)} vocab, {len(phrasal_verbs)} phrasal, {len(idioms)} idioms")
        print(f"🔄 Total regenerations: {final_state.get('regeneration_count', 0)}")
        
        # Check if we hit the limit and warn user
        if final_state.get('regeneration_count', 0) >= max_regenerations:
            print(f"⚠️ WARNING: Hit max regeneration limit ({max_regenerations})")
            print(f"📊 Requested: {vocab_per_batch} vocab, {phrasal_verbs_per_batch} phrasal, {idioms_per_batch} idioms")
            print(f"📊 Got: {len(vocabularies)} vocab, {len(phrasal_verbs)} phrasal, {len(idioms)} idioms")
        
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
    Generate vocabulary using react agent approach with regeneration loop
    """
    try:
        print(f"🚀 Starting react agent vocabulary generation for '{topic}'")
        
        # Use the regeneration loop instead of direct tool call
        return generate_vocab_with_regeneration_loop(
            topic=topic,
            level=level,
            target_language=target_language,
            original_language=original_language,
            vocab_per_batch=vocab_per_batch,
            phrasal_verbs_per_batch=phrasal_verbs_per_batch,
            idioms_per_batch=idioms_per_batch,
            user_id=user_id,
            ai_role=ai_role,
               max_regenerations=3
        )
        
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
            "lookback_days": 2
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
