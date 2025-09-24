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
    search_context: str
    
    # Validation and tracking
    validation_results: List[dict]
    generation_attempts: int
    max_attempts: int
    
    # User preferences
    user_id: str
    ai_role: str
    
    # Messages for react agent
    messages: Annotated[List, operator.add]
    
    # Required for react agent
    remaining_steps: int

# =========== Tools for React Agent ===========

@tool
def generate_vocabulary_tool(topic: str, level: str, target_language: str, original_language: str, 
                           vocab_count: int = 10, phrasal_verbs_count: int = 0, idioms_count: int = 0) -> str:
    """Generate vocabulary entries for a given topic and level"""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser
        from pydantic import BaseModel, Field
        from typing import List
        
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
        
        # Enhanced prompt for diversity and quality
        prompt = f'''You are an expert {target_language} language teacher. Generate diverse, high-quality vocabulary for the topic "{topic}" at {level} level.

TOPIC: {topic}
LEVEL: {level}
TARGET LANGUAGE: {target_language}
ORIGINAL LANGUAGE: {original_language}

GENERATION REQUIREMENTS:
- Create {vocab_count} vocabulary words
- Create {phrasal_verbs_count} phrasal verbs  
- Create {idioms_count} idioms

QUALITY REQUIREMENTS:
- All words must be directly relevant to "{topic}"
- Ensure appropriate difficulty for {level} level
- Generate diverse, engaging, and useful vocabulary
- Avoid repetition and generic terms
- Include clear, detailed definitions
- Provide realistic example sentences
- Ensure accurate translations

For each entry, include:
- word: the vocabulary word
- definition: clear definition in {target_language}
- example: practical example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: part of speech (noun, verb, adjective, adverb, etc.)

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
        
        result = structured_llm.invoke(prompt)
        
        # Convert to VocabEntry objects
        vocab_entries = []
        
        # Process vocabularies
        for vocab in result.vocabularies:
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
        
        # Process phrasal verbs
        for pv in result.phrasal_verbs:
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
        
        # Process idioms
        for idiom in result.idioms:
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
        
        return f"Successfully generated {len(vocab_entries)} vocabulary entries for {topic}. Words: {', '.join([entry.word for entry in vocab_entries[:5]])}"
        
    except Exception as e:
        return f"Error generating vocabulary: {str(e)}"

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
        search_topic_context
    ]
    
    # Create react agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_schema=VocabState
    )
    
    return agent

# =========== Main Generation Function ===========

def generate_vocab_with_react_agent(
    topic: str,
    level: CEFRLevel,
    target_language: str = "English",
    original_language: str = "Vietnamese",
    vocab_per_batch: int = 10,
    phrasal_verbs_per_batch: int = 0,
    idioms_per_batch: int = 0,
    user_id: str = "default_user",
    ai_role: str = "Language Teacher",
    avoid_words: list = None
) -> VocabGenerationResponse:
    """
    Generate vocabulary using react agent approach
    """
    try:
        print(f"🚀 Starting react agent vocabulary generation for '{topic}'")
        
        # Create react agent
        agent = create_vocab_react_agent()
        
        # Create detailed system message
        system_message = f"""You are a {ai_role} helping to generate diverse, high-quality vocabulary for language learning.

Your task:
1. Generate vocabulary for topic: {topic}
2. Level: {level.value}
3. Target language: {target_language}
4. Original language: {original_language}
5. Generate exactly {vocab_per_batch} vocabulary words, {phrasal_verbs_per_batch} phrasal verbs, {idioms_per_batch} idioms

IMPORTANT INSTRUCTIONS:
- Use the generate_vocabulary_tool to create the vocabulary
- Ensure all words are relevant to the topic "{topic}"
- Make sure the vocabulary is appropriate for {level.value} level
- Generate diverse, high-quality words (not generic or repetitive)
- Provide clear definitions and practical examples
- Include accurate translations

Use the available tools to complete this task efficiently."""
        
        # Create human message
        human_message = f"Please generate {vocab_per_batch} vocabulary words for the topic '{topic}' at {level.value} level in {target_language} with translations to {original_language}. Make sure the words are diverse and high-quality."
        
        # Run the agent
        result = agent.invoke({
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": human_message}
            ]
        })
        
        print(f"✅ React agent completed vocabulary generation")
        
        # The react agent doesn't store vocab entries in state, so we need to extract from tool calls
        # Let's generate the vocabulary directly using our tool
        print(f"🔧 Extracting vocabulary from react agent response...")
        
        # Generate vocabulary directly using our tool
        vocab_result = generate_vocabulary_tool.invoke({
            "topic": topic,
            "level": level.value,
            "target_language": target_language,
            "original_language": original_language,
            "vocab_count": vocab_per_batch,
            "phrasal_verbs_count": phrasal_verbs_per_batch,
            "idioms_count": idioms_per_batch
        })
        
        print(f"📊 Tool result: {vocab_result}")
        
        # The tool is generating real vocabulary, but we need to extract it properly
        # Let's call the tool directly to get the actual vocabulary entries
        print(f"🔧 Generating actual vocabulary entries...")
        
        # Create a temporary tool instance to get the actual entries
        from langchain_openai import ChatOpenAI
        from pydantic import BaseModel, Field
        from typing import List
        
        # Define structured output
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
        
        # Create structured LLM
        structured_llm = llm.with_structured_output(VocabResponse, method="function_calling")
        
        # Enhanced prompt for diversity and quality with randomization
        import random
        import time
        
        # Add randomization elements to encourage diversity
        diversity_techniques = [
            "focus on specific aspects and subcategories",
            "explore different perspectives and use cases", 
            "include both common and specialized terms",
            "cover various contexts and applications",
            "emphasize practical and everyday usage",
            "highlight modern and contemporary terms"
        ]
        
        selected_technique = random.choice(diversity_techniques)
        random_seed = int(time.time() * 1000) % 1000
        
        # Create diverse prompt variations
        prompt_variations = [
            f'''You are an expert {target_language} language teacher. Generate diverse, high-quality vocabulary for the topic "{topic}" at {level.value} level.

TOPIC: {topic}
LEVEL: {level.value}
TARGET LANGUAGE: {target_language}
ORIGINAL LANGUAGE: {original_language}
DIVERSITY FOCUS: {selected_technique}

GENERATION REQUIREMENTS:
- Create {vocab_per_batch} vocabulary words
- Create {phrasal_verbs_per_batch} phrasal verbs  
- Create {idioms_per_batch} idioms

DIVERSITY REQUIREMENTS:
- AVOID common, obvious words that always appear for this topic
- Focus on {selected_technique}
- Generate unique, less common but still relevant vocabulary
- Ensure each word is distinct and different from typical lists
- Include both basic and intermediate terms
- Cover different aspects of the topic

QUALITY REQUIREMENTS:
- All words must be directly relevant to "{topic}"
- Ensure appropriate difficulty for {level.value} level
- Generate diverse, engaging, and useful vocabulary
- Avoid repetition and generic terms
- Include clear, detailed definitions
- Provide realistic example sentences
- Ensure accurate translations

For each entry, include:
- word: the vocabulary word
- definition: clear definition in {target_language}
- example: practical example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: part of speech (noun, verb, adjective, adverb, etc.)

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.''',
            
            f'''You are a creative {target_language} language teacher specializing in diverse vocabulary generation.

TOPIC: {topic}
LEVEL: {level.value}
TARGET LANGUAGE: {target_language}
ORIGINAL LANGUAGE: {original_language}

CREATIVE CHALLENGE:
Generate vocabulary that is:
- Relevant to "{topic}" but NOT the most obvious choices
- Appropriate for {level.value} level learners
- Diverse and varied in their focus areas
- Useful and practical for real-world use

GENERATION REQUIREMENTS:
- Create {vocab_per_batch} vocabulary words
- Create {phrasal_verbs_per_batch} phrasal verbs  
- Create {idioms_per_batch} idioms

AVOID these common words for {topic}: computer, internet, software, device, application, system, data, network, digital, online

Instead, focus on:
- Specific tools, processes, or concepts
- Action words and descriptive terms
- Modern terminology and trends
- Practical applications and uses
- Phrasal verbs related to technology actions
- Idioms and expressions used in tech contexts

For each entry, include:
- word: the vocabulary word
- definition: clear definition in {target_language}
- example: practical example sentence in {target_language}
- translation: accurate translation to {original_language}
- example_translation: translation of the example sentence to {original_language}
- part_of_speech: part of speech (noun, verb, adjective, adverb, etc.)

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''
        ]
        
        # Select prompt variation based on random seed
        prompt = prompt_variations[random_seed % len(prompt_variations)]
        
        # Add avoid_words to prompt if provided
        if avoid_words and len(avoid_words) > 0:
            avoid_list = ", ".join(avoid_words)
            prompt += f"\n\nIMPORTANT: AVOID these words that were already generated: {avoid_list}"
            prompt += f"\nGenerate completely different vocabulary that doesn't overlap with these words."
        
        result = structured_llm.invoke(prompt)
        
        # Convert to VocabEntry objects
        vocab_entries = []
        
        # Process vocabularies
        for vocab in result.vocabularies:
            entry = VocabEntry(
                word=vocab.word,
                definition=vocab.definition,
                example=vocab.example,
                translation=vocab.translation,
                example_translation=vocab.example_translation,
                part_of_speech=PartOfSpeech(vocab.part_of_speech),
                level=level
            )
            vocab_entries.append(entry)
        
        # Process phrasal verbs
        for pv in result.phrasal_verbs:
            entry = VocabEntry(
                word=pv.word,
                definition=pv.definition,
                example=pv.example,
                translation=pv.translation,
                example_translation=pv.example_translation,
                part_of_speech=PartOfSpeech('phrasal_verb'),
                level=level
            )
            vocab_entries.append(entry)
        
        # Process idioms
        for idiom in result.idioms:
            entry = VocabEntry(
                word=idiom.word,
                definition=idiom.definition,
                example=idiom.example,
                translation=idiom.translation,
                example_translation=idiom.example_translation,
                part_of_speech=PartOfSpeech('idiom'),
                level=level
            )
            vocab_entries.append(entry)
        
        print(f"✅ Generated {len(vocab_entries)} actual vocabulary entries")
        
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

# =========== Export Functions ===========

def get_topic_list_export():
    """Export topic list function"""
    return get_topic_list()

def get_categories_export():
    """Export categories function"""
    return get_categories()

def get_topics_by_category_export(category: str):
    """Export topics by category function"""
    return get_topics_by_category(category)
