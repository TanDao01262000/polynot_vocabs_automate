# AI Vocabulary Generator API

A FastAPI-based vocabulary generation service with user management and Supabase integration.

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

## 🧪 Testing the API

### Health Check
```bash
curl http://localhost:8001/health
```

### Generate Vocabulary
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

### Test Endpoints
```bash
# Test save functionality
curl -X POST http://localhost:8001/vocab/test-save \
  -H "Authorization: Bearer YOUR_USER_ID"

# Test list functionality
curl -X GET http://localhost:8001/vocab/test-list \
  -H "Authorization: Bearer YOUR_USER_ID"
```

## 🏗️ Development

### Auto-Reload
The development server automatically reloads when you make changes to your code files. No need to rebuild the container!

### File Structure
```
├── vocab_api.py           # Main FastAPI application
├── models.py              # Data models
├── supabase_database.py   # Database operations
├── vocab_agent.py         # Vocabulary generation logic
├── config.py              # Configuration
├── topics.py              # Topic management
├── docker-compose.yml     # Docker configuration
├── Dockerfile             # Container definition
└── requirements.txt       # Python dependencies
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

### Generation
- `POST /generate/single` - Generate vocabulary for single topic
- `POST /generate/multiple` - Generate vocabulary for multiple topics
- `POST /generate/category` - Generate vocabulary for category

### User Vocabulary
- `GET /vocab/user-saved` - Get user's saved vocabulary
- `POST /vocab/save` - Save vocabulary to user's list
- `POST /vocab/hide-toggle` - Hide/unhide vocabulary
- `POST /vocab/review-toggle` - Mark/unmark as reviewed

### Topics
- `GET /categories` - Get all categories
- `GET /topics/{category}` - Get topics by category
- `GET /topics` - Get all topics

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
