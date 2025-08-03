from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# Import your existing modules
from vocab_agent import run_single_topic_generation, run_continuous_vocab_generation, view_saved_topic_lists
from models import CEFRLevel
from config import Config
from topics import get_categories, get_topics_by_category, get_topic_list

# Initialize FastAPI app
app = FastAPI(
    title="AI Vocabulary Generator API - Comprehensive",
    description="Complete API for generating vocabulary content with all available methods",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for Flutter frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========== Pydantic Models ===========

class GenerateSingleRequest(BaseModel):
    topic: str
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3
    save_topic_list: bool = False
    topic_list_name: Optional[str] = None

class GenerateMultipleRequest(BaseModel):
    topics: List[str]
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3
    save_topic_list: bool = False
    topic_list_name: Optional[str] = None

class GenerateCategoryRequest(BaseModel):
    category: str
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3

class VocabEntryResponse(BaseModel):
    word: str
    definition: str
    part_of_speech: str
    example: str
    example_translation: str
    level: str
    is_duplicate: bool = False

class GenerateResponse(BaseModel):
    success: bool
    message: str
    method: str
    details: dict
    generated_vocabulary: List[VocabEntryResponse]
    total_generated: int
    new_entries_saved: int
    duplicates_found: int

class TopicListResponse(BaseModel):
    topics: List[str]
    description: str

class CategoryResponse(BaseModel):
    categories: List[str]

# =========== Generation Functions ===========

def generate_single_topic_sync(
    topic: str,
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int,
    save_topic_list: bool,
    topic_list_name: Optional[str]
):
    """Generate vocabulary for a single topic synchronously"""
    try:
        print(f"Starting single topic generation for: {topic}")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        # Get existing combinations
        existing_combinations = get_existing_combinations_for_topic(topic)
        print(f"Found {len(existing_combinations)} existing combinations")
        
        # Create prompt
        prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

        # Generate vocabulary
        res = structured_llm.invoke(prompt)
        
        # Combine all entries
        all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
        
        print(f"Generated {len(all_entries)} entries")
        
        # Validate topic relevance
        relevant_entries = validate_topic_relevance(all_entries, topic)
        print(f"Topic-relevant entries: {len(relevant_entries)}")
        
        # Filter out duplicates for database storage only
        filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
        
        # Create response entries with duplicate flags
        response_entries = []
        for entry in relevant_entries:
            is_duplicate = entry not in filtered_entries
            response_entries.append(VocabEntryResponse(
                word=entry.word,
                definition=entry.definition,
                part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                example=entry.example,
                example_translation=entry.example_translation,
                level=entry.level.value,
                is_duplicate=is_duplicate
            ))
        
        if filtered_entries:
            print(f"Saving {len(filtered_entries)} new entries to database...")
            
            # Save to database
            db.insert_vocab_entries(
                entries=filtered_entries,
                topic_name=topic,
                target_language=language_to_learn,
                original_language=learners_native_language
            )
            print("Saved successfully!")
        else:
            print("No new entries to save (all were duplicates)")
            
        return {
            "vocabulary": response_entries,
            "total_generated": len(response_entries),
            "new_entries_saved": len(filtered_entries),
            "duplicates_found": len(response_entries) - len(filtered_entries)
        }
            
    except Exception as e:
        print(f"Error in single topic generation: {e}")
        raise

def generate_multiple_topics_sync(
    topics: List[str],
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int,
    save_topic_list: bool,
    topic_list_name: Optional[str]
):
    """Generate vocabulary for multiple topics synchronously"""
    try:
        print(f"Starting multiple topics generation for: {', '.join(topics)}")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        all_response_entries = []
        total_new_saved = 0
        total_duplicates = 0
        
        for topic in topics:
            print(f"\nProcessing topic: {topic}")
            
            # Get existing combinations
            existing_combinations = get_existing_combinations_for_topic(topic)
            print(f"Found {len(existing_combinations)} existing combinations")
            
            # Create prompt
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            # Generate vocabulary
            res = structured_llm.invoke(prompt)
            
            # Combine all entries
            all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
            
            print(f"Generated {len(all_entries)} entries")
            
            # Validate topic relevance
            relevant_entries = validate_topic_relevance(all_entries, topic)
            print(f"Topic-relevant entries: {len(relevant_entries)}")
            
            # Filter out duplicates for database storage only
            filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
            
            # Create response entries with duplicate flags
            for entry in relevant_entries:
                is_duplicate = entry not in filtered_entries
                all_response_entries.append(VocabEntryResponse(
                    word=entry.word,
                    definition=entry.definition,
                    part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                    example=entry.example,
                    example_translation=entry.example_translation,
                    level=entry.level.value,
                    is_duplicate=is_duplicate
                ))
            
            if filtered_entries:
                print(f"Saving {len(filtered_entries)} new entries to database...")
                
                # Save to database
                db.insert_vocab_entries(
                    entries=filtered_entries,
                    topic_name=topic,
                    target_language=language_to_learn,
                    original_language=learners_native_language
                )
                print("Saved successfully!")
                total_new_saved += len(filtered_entries)
            else:
                print("No new entries to save (all were duplicates)")
            
            total_duplicates += len(relevant_entries) - len(filtered_entries)
                
        return {
            "vocabulary": all_response_entries,
            "total_generated": len(all_response_entries),
            "new_entries_saved": total_new_saved,
            "duplicates_found": total_duplicates
        }
                
    except Exception as e:
        print(f"Error in multiple topics generation: {e}")
        raise

def generate_category_sync(
    category: str,
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int
):
    """Generate vocabulary for category synchronously"""
    try:
        print(f"Starting category generation for: {category}")
        
        # Get topics for this category
        topics = get_topic_list(category)
        print(f"Found {len(topics)} topics in category '{category}'")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        all_response_entries = []
        total_new_saved = 0
        total_duplicates = 0
        
        for topic in topics:
            print(f"\nProcessing topic: {topic}")
            
            # Get existing combinations
            existing_combinations = get_existing_combinations_for_topic(topic)
            print(f"Found {len(existing_combinations)} existing combinations")
            
            # Create prompt
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            # Generate vocabulary
            res = structured_llm.invoke(prompt)
            
            # Combine all entries
            all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
            
            print(f"Generated {len(all_entries)} entries")
            
            # Validate topic relevance
            relevant_entries = validate_topic_relevance(all_entries, topic)
            print(f"Topic-relevant entries: {len(relevant_entries)}")
            
            # Filter out duplicates for database storage only
            filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
            
            # Create response entries with duplicate flags
            for entry in relevant_entries:
                is_duplicate = entry not in filtered_entries
                all_response_entries.append(VocabEntryResponse(
                    word=entry.word,
                    definition=entry.definition,
                    part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                    example=entry.example,
                    example_translation=entry.example_translation,
                    level=entry.level.value,
                    is_duplicate=is_duplicate
                ))
            
            if filtered_entries:
                print(f"Saving {len(filtered_entries)} new entries to database...")
                
                # Save to database
                db.insert_vocab_entries(
                    entries=filtered_entries,
                    topic_name=topic,
                    category_name=category,
                    target_language=language_to_learn,
                    original_language=learners_native_language
                )
                print("Saved successfully!")
                total_new_saved += len(filtered_entries)
            else:
                print("No new entries to save (all were duplicates)")
            
            total_duplicates += len(relevant_entries) - len(filtered_entries)
                
        return {
            "vocabulary": all_response_entries,
            "total_generated": len(all_response_entries),
            "new_entries_saved": total_new_saved,
            "duplicates_found": total_duplicates
        }
                
    except Exception as e:
        print(f"Error in category generation: {e}")
        raise

# =========== API Endpoints ===========

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "AI Vocabulary Generator API - Comprehensive",
        "version": "11.0.0",
        "docs": "/docs",
        "status": "running",
        "available_endpoints": [
            "POST /generate/single - Generate for single topic",
            "POST /generate/multiple - Generate for multiple topics",
            "POST /generate/category - Generate for category",
            "GET /categories - Get all categories",
            "GET /topics/{category} - Get topics by category",
            "GET /topics - Get all topics"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2025-08-02T16:00:00.000Z"}

@app.post("/generate/single", response_model=GenerateResponse, tags=["Generation"])
async def generate_single_topic(request: GenerateSingleRequest):
    """Generate vocabulary for a single topic"""
    try:
        # Generate vocabulary synchronously
        result = generate_single_topic_sync(
            topic=request.topic,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds,
            save_topic_list=request.save_topic_list,
            topic_list_name=request.topic_list_name
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for topic '{request.topic}' at {request.level.value} level",
            method="single_topic",
            details={
                "topic": request.topic,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.post("/generate/multiple", response_model=GenerateResponse, tags=["Generation"])
async def generate_multiple_topics(request: GenerateMultipleRequest):
    """Generate vocabulary for multiple topics"""
    try:
        # Generate vocabulary synchronously
        result = generate_multiple_topics_sync(
            topics=request.topics,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds,
            save_topic_list=request.save_topic_list,
            topic_list_name=request.topic_list_name
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for {len(request.topics)} topics at {request.level.value} level",
            method="multiple_topics",
            details={
                "topics": request.topics,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.post("/generate/category", response_model=GenerateResponse, tags=["Generation"])
async def generate_category(request: GenerateCategoryRequest):
    """Generate vocabulary for all topics in a category"""
    try:
        # Validate category
        categories = get_categories()
        if request.category not in categories:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid category '{request.category}'. Available categories: {categories}"
            )
        
        # Generate vocabulary synchronously
        result = generate_category_sync(
            category=request.category,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for category '{request.category}' at {request.level.value} level",
            method="category",
            details={
                "category": request.category,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.get("/categories", response_model=CategoryResponse, tags=["Topics"])
async def get_categories_endpoint():
    """Get all available topic categories"""
    try:
        categories = get_categories()
        return CategoryResponse(categories=categories)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get categories: {str(e)}")

@app.get("/topics/{category}", response_model=TopicListResponse, tags=["Topics"])
async def get_topics_by_category_endpoint(category: str):
    """Get topics for a specific category"""
    try:
        topic_list = get_topics_by_category(category)
        return TopicListResponse(
            topics=topic_list.topics,
            description=topic_list.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get topics: {str(e)}")

@app.get("/topics", response_model=TopicListResponse, tags=["Topics"])
async def get_all_topics_endpoint():
    """Get all available topics"""
    try:
        all_topics = get_topic_list()
        return TopicListResponse(
            topics=all_topics,
            description="All available topics from all categories"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get topics: {str(e)}")

# =========== Main Application ===========

if __name__ == "__main__":
    # Validate configuration
    try:
        Config.validate()
        print("✅ Configuration validated successfully")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        exit(1)
    
    # Run the API server
    uvicorn.run(
        "api_comprehensive:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 