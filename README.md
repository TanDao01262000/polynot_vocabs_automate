# AI Vocabulary Generator API

A comprehensive FastAPI-based vocabulary generation service with advanced flashcard system, user management, and Supabase integration.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Supabase credentials (see Configuration section)

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd polynot_AI_automate_vocab
```

### 2. Set up environment variables
Create a `.env` file in the root directory:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

### 3. Run with Docker (Development)
```bash
# Start the development server with auto-reload
make dev

# OR start in background
make dev-d
```

The server will be available at: http://localhost:8001

## 🐳 Docker Commands

### Using Makefile (Recommended)
```bash
# Development (with auto-reload)
make dev          # Start server with logs
make dev-d        # Start server in background
make logs         # View logs
make stop         # Stop server
make restart      # Restart server
make clean        # Stop and clean up everything
```

### Using Docker Compose directly
```bash
# Start development server
docker-compose up --build

# Start in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop server
docker-compose down
```

## 🔧 Configuration

### Environment Variables
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_ANON_KEY`: Your Supabase anonymous key

### Port Configuration
- **API Server**: 8001
- **Documentation**: http://localhost:8001/docs

## 📚 API Documentation

Once the server is running, you can access:
- **Interactive API Docs**: http://localhost:8001/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8001/redoc (ReDoc)

## 🧪 Testing

### Run All Tests
```bash
# Run comprehensive test suite
make test

# Run tests locally (without Docker)
make test-local

# Run specific tests
make test-flashcard
make test-comprehensive
```

### Manual API Testing

#### Health Check
```bash
curl http://localhost:8001/health
```

#### Generate Vocabulary
```bash
curl -X POST http://localhost:8001/generate/single \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "food",
    "level": "A2",
    "language_to_learn": "English",
    "learners_native_language": "Vietnamese"
  }'
```

#### Test Flashcard System
```bash
# Get study modes
curl http://localhost:8001/flashcard/study-modes

# Create quick session
curl -X POST http://localhost:8001/flashcard/quick-session \
  -H "Content-Type: application/json" \
  -H "Authorization: YOUR_USER_ID" \
  -d '{
    "study_mode": "mixed",
    "max_cards": 5,
    "session_type": "daily_review"
  }'
```

## 🏗️ Development

### Auto-Reload
The development server automatically reloads when you make changes to your code files. No need to rebuild the container!

### File Structure
```
├── vocab_api.py           # Main FastAPI application
├── models.py              # Data models and schemas
├── supabase_database.py   # Database operations
├── vocab_agent.py         # Vocabulary generation logic
├── config.py              # Configuration management
├── topics.py              # Topic management
├── main.py                # CLI examples and demos
├── run_tests.py           # Test runner script
├── tests/                 # Test files
│   ├── test_flashcard_system.py
│   ├── test_flashcard_endpoints.py
│   ├── test_flashcard_with_data.py
│   └── comprehensive_test_suite.py
├── scripts/               # Utility scripts
│   ├── check_users.py
│   ├── apply_rls_fix.py
│   └── setup_flashcard_tables.py
├── docs/                  # Documentation
│   ├── FLASHCARD_README.md
│   ├── FLASHCARD_SETUP.md
│   ├── flashcard_schema.sql
│   └── FLASHCARD_TEST_RESULTS.md
├── docker-compose.yml     # Docker configuration
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
├── Makefile              # Build and test commands
└── README.md             # This file
```

### Making Changes
1. Start the development server: `make dev`
2. Edit your code files
3. Server automatically reloads
4. Test your changes immediately

## 🚀 Production

For production deployment:
```bash
# Build production image
docker build -t vocab-api .

# Run production container
docker run -p 8001:8001 vocab-api
```

## 🐛 Troubleshooting

### Container won't start
```bash
# Clean up and restart
make clean
make dev
```

### Port already in use
```bash
# Check what's using port 8001
lsof -i :8001

# Kill the process or change port in docker-compose.yml
```

### Permission issues
```bash
# Make sure Docker has access to your directory
sudo chown -R $USER:$USER .
```

## 📝 Available Endpoints

### Core API
- `GET /` - API information and status
- `GET /health` - Health check endpoint

### Vocabulary Generation
- `POST /generate/single` - Generate vocabulary for single topic
- `POST /generate/multiple` - Generate vocabulary for multiple topics
- `POST /generate/category` - Generate vocabulary for category

### User Vocabulary Management
- `GET /vocab/list` - Get paginated vocabulary list with filters
- `GET /vocab/user-saved` - Get user's saved vocabulary
- `POST /vocab/save-to-user` - Save vocabulary to user's list
- `POST /vocab/favorite` - Toggle favorite status
- `POST /vocab/hide` - Hide/unhide vocabulary
- `POST /vocab/review` - Mark/unmark as reviewed
- `POST /vocab/note` - Add personal notes
- `POST /vocab/rate` - Rate difficulty (1-5)

### Vocabulary Lists
- `POST /vocab/lists` - Create vocabulary list
- `GET /vocab/lists` - Get user's vocabulary lists
- `POST /vocab/lists/{id}/add` - Add vocab to list
- `DELETE /vocab/lists/{id}/remove` - Remove vocab from list

### Advanced Flashcard System
- `POST /flashcard/session/create` - Create flashcard session
- `GET /flashcard/session/{id}/current` - Get current card
- `POST /flashcard/session/{id}/answer` - Submit answer
- `POST /flashcard/quick-session` - Create quick session
- `GET /flashcard/sessions` - Get user's sessions
- `GET /flashcard/stats` - Get flashcard statistics
- `GET /flashcard/analytics` - Get analytics data
- `GET /flashcard/review-cards` - Get cards due for review

### Study Configuration
- `GET /flashcard/study-modes` - Get available study modes
- `GET /flashcard/session-types` - Get session types
- `GET /flashcard/difficulty-ratings` - Get difficulty ratings

### Topics & Categories
- `GET /categories` - Get all categories
- `GET /topics/{category}` - Get topics by category
- `GET /topics` - Get all topics

### Testing Endpoints
- `POST /test/create-user` - Create test user
- `POST /vocab/test-save` - Test save functionality
- `GET /vocab/test-list` - Test list functionality

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `make dev`
5. Submit a pull request

## 📄 License

[Your License Here]

---

**Happy coding! 🎉**
