---
title: Flask AI Backend
emoji: 🤖
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

#  Flask AI Agent - Complete Production System

A production-ready AI agent system with Flask API backend, Streamlit frontend, WebSocket streaming, database persistence, and JWT authentication.

##  Features

-  **RESTful API** - Clean Flask API architecture
-  **Beautiful UI** - Streamlit frontend with modern design
-  **Authentication** - JWT tokens + API keys
-  **Database** - SQLite (local) / PostgreSQL (production)
-  **WebSocket** - Real-time streaming chat
-  **History** - Persistent conversation storage
-  **Markdown** - Rich formatted responses
-  **Free LLM** - Google Gemini 2.0 Flash

---

##  Project Structure

```
flask-ai-agent/
├── app.py                 # Main Flask API
├── streamlit_app.py       # Frontend UI
├── requirements.txt       # Dependencies
├── .env                   # Environment variables (create this)
├── .env.example          # Template for .env
├── .gitignore            # Git ignore file
└── README.md             # This file
```

---

##  Quick Start (Local Development)

### 1. Clone/Create Project

```bash
mkdir flask-ai-agent
cd flask-ai-agent
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Activate:
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup Environment Variables

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```env
GOOGLE_API_KEY=your_actual_gemini_api_key_here
```

Get free Gemini API key: https://makersuite.google.com/app/apikey

### 5. Run the Application

**Terminal 1 - API Server:**
```bash
python app.py
```

**Terminal 2 - Streamlit UI:**
```bash
streamlit run streamlit_app.py
```

**Access:**
- API: http://localhost:5000
- UI: http://localhost:8501

---

##  Deploy to Render (Free Hosting)

### Step 1: Prepare Code for GitHub

Create `.gitignore`:

```gitignore
venv/
__pycache__/
*.pyc
.env
*.db
.DS_Store
```

Initialize Git:

```bash
git init
git add .
git commit -m "Initial commit"
```

### Step 2: Push to GitHub

```bash
# Create repo on GitHub first, then:
git remote add origin https://github.com/YOUR_USERNAME/flask-ai-agent.git
git branch -M main
git push -u origin main
```

### Step 3: Deploy Flask API on Render

1. Go to https://render.com
2. Sign up/Login with GitHub
3. Click **"New +"** → **"Web Service"**
4. Select your `flask-ai-agent` repository
5. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `flask-ai-agent-api` |
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app` |
| **Plan** | Free |

6. Click **"Advanced"** → Add Environment Variables:

```
GOOGLE_API_KEY = your_gemini_api_key
SECRET_KEY = random_secret_key_here
JWT_SECRET_KEY = another_random_key_here
```

7. Click **"Create Web Service"**
8. Wait 3-5 minutes for deployment
9. Copy your API URL (e.g., `https://flask-ai-agent-api.onrender.com`)

### Step 4: Deploy Streamlit UI on Render

1. Click **"New +"** → **"Web Service"** again
2. Select same repository
3. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `flask-ai-agent-ui` |
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0` |
| **Plan** | Free |

4. Add Environment Variable:

```
API_URL = https://flask-ai-agent-api.onrender.com
```

5. Click **"Create Web Service"**
6. Access your UI at the provided URL!

---

## 📡 API Endpoints

### Authentication

**Register User**
```bash
POST /api/auth/register
Content-Type: application/json

{
  "username": "john",
  "email": "john@example.com",
  "password": "secure123"
}
```

**Login**
```bash
POST /api/auth/login
Content-Type: application/json

{
  "username": "john",
  "password": "secure123"
}

Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "api_key": "sk-...",
  "username": "john"
}
```

### Chat

**Send Message**
```bash
POST /api/chat
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json

{
  "message": "Explain async/await in Python",
  "conversation_id": 1  // optional
}

Response:
{
  "response": "Markdown formatted response...",
  "html": "<p>HTML version...</p>",
  "conversation_id": 1,
  "timestamp": "2026-01-12T10:30:00"
}
```

**Get Conversations**
```bash
GET /api/conversations
Authorization: Bearer YOUR_JWT_TOKEN
```

**Get Specific Conversation**
```bash
GET /api/conversations/{id}
Authorization: Bearer YOUR_JWT_TOKEN
```

### WebSocket (Real-time)

```javascript
const socket = io('https://your-api-url.com');

socket.on('connect', () => {
  console.log('Connected!');
});

socket.emit('chat_message', {
  message: 'Hello AI!',
  token: 'your_jwt_token'
});

socket.on('chat_chunk', (data) => {
  console.log(data.chunk); // Streamed word by word
});
```

---

##  Customize Agent Types

Edit `app.py` and modify `AGENT_PROMPTS`:

```python
AGENT_PROMPTS = {
    "your_custom_agent": """You are a specialized AI that does...
    
    Your capabilities:
    - Skill 1
    - Skill 2
    - Skill 3
    """,
}
```

Set environment variable:
```bash
AGENT_TYPE=your_custom_agent
```

---

## 🔧 Troubleshooting

**Issue: Port already in use**
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9
```

**Issue: Database locked**
```bash
# Delete and recreate database
rm agent.db
python app.py  # Will auto-create new DB
```

**Issue: Module not found**
```bash
pip install -r requirements.txt --upgrade
```

**Issue: API key not working**
- Verify key in .env file
- Restart server after changing .env
- Check Gemini API quota: https://makersuite.google.com

---

##  Advanced Features

### Add PostgreSQL (Production Database)

On Render:
1. Create PostgreSQL database
2. Copy `DATABASE_URL`
3. Add to environment variables
4. Restart service

### Add Rate Limiting

```bash
pip install flask-limiter
```

```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    default_limits=["100 per hour"]
)

@app.route('/api/chat')
@limiter.limit("20 per minute")
def chat():
    # ...
```

### Add Caching

```bash
pip install flask-caching
```

```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@app.route('/api/status')
@cache.cached(timeout=60)
def status():
    # ...
```

---

##  License

MIT License - Feel free to use in your projects!

---

##  Contributing

Pull requests welcome! For major changes, please open an issue first.

---

##  Support

Issues? Open a GitHub issue or contact support.

---

##  What's Next?

- [ ] Add file upload support
- [ ] Implement RAG (vector search)
- [ ] Add more LLM providers (OpenAI, Anthropic)
- [ ] Mobile app (React Native)
- [ ] Voice input/output
- [ ] Multi-language support

---

**Built with  using Flask, Streamlit, and Google Gemini**