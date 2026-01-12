# ╔════════════════════════════════════════════════════════════════════╗
# ║                     app.py - Main Flask API                        ║
# ║  WebSocket • Database • Auth • Ready for Render deployment         ║
# ╚════════════════════════════════════════════════════════════════════╝

from flask import Flask, request, jsonify, render_template_string, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import google.generativeai as genai
import os
import markdown
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)

# Database configuration (SQLite for simplicity, can use PostgreSQL on Render)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///agent.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
db = SQLAlchemy(app)
jwt = JWTManager(app)

# LLM Configuration
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
AGENT_TYPE = os.environ.get('AGENT_TYPE', 'coding_assistant')

# ══════════════════════════════════════════════════════════════════════
# DATABASE MODELS
# ══════════════════════════════════════════════════════════════════════

class User(db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    conversations = db.relationship('Conversation', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Conversation(db.Model):
    """Conversation history model"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = db.relationship('Message', backref='conversation', lazy=True)

class Message(db.Model):
    """Individual message model"""
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    tokens = db.Column(db.Integer, default=0)

# Create tables
with app.app_context():
    db.create_all()
    
    # Create guest user if not exists
    if not User.query.filter_by(username='guest').first():
        guest = User(
            username='guest',
            email='guest@example.com',
            api_key='guest_key',
            password_hash='guest'
        )
        db.session.add(guest)
        db.session.commit()

# ══════════════════════════════════════════════════════════════════════
# LLM SETUP
# ══════════════════════════════════════════════════════════════════════

AGENT_PROMPTS = {
    "coding_assistant": """You are an expert software engineer.
Provide clean code, explanations, and best practices.
Format code in markdown with syntax highlighting.""",
    
    "data_analyst": """You are a senior data scientist.
Provide data analysis code, visualizations, and insights.
Use pandas, numpy, and visualization libraries.""",
    
    "creative_writer": """You are a creative writer and storyteller.
Write engaging narratives, stories, and creative content.""",
    
    "tutor": """You are a patient educational tutor.
Explain concepts clearly with examples and practice problems."""
}

def get_llm_model():
    """Initialize Gemini model"""
    if not GOOGLE_API_KEY:
        return None
    
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        system_prompt = AGENT_PROMPTS.get(AGENT_TYPE, AGENT_PROMPTS['coding_assistant'])
        model = genai.GenerativeModel(
            model_name='gemini-2.0-flash-exp',
            system_instruction=system_prompt
        )
        return model
    except Exception as e:
        print(f"LLM setup error: {e}")
        return None

model = get_llm_model()

# ══════════════════════════════════════════════════════════════════════
# AUTHENTICATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not all([username, email, password]):
            return jsonify({"error": "Missing required fields"}), 400
        
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Username already exists"}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email already exists"}), 400
        
        # Create new user
        user = User(
            username=username,
            email=email,
            api_key=secrets.token_urlsafe(32)
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Generate JWT token
        access_token = create_access_token(identity=user.id)
        
        return jsonify({
            "message": "User registered successfully",
            "access_token": access_token,
            "api_key": user.api_key
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid credentials"}), 401
        
        access_token = create_access_token(identity=user.id)
        
        return jsonify({
            "access_token": access_token,
            "api_key": user.api_key,
            "username": user.username
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        messages = Message.query.filter_by(
            conversation_id=conversation_id
        ).order_by(Message.timestamp).all()
        
        return jsonify({
            "conversation": {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat()
            },
            "messages": [{
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            } for m in messages]
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════════════════════════
# WEBSOCKET SUPPORT FOR REAL-TIME STREAMING
# ══════════════════════════════════════════════════════════════════════

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    print('Client connected')
    emit('status', {'message': 'Connected to AI Agent'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    print('Client disconnected')

@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle real-time chat via WebSocket"""
    try:
        message = data.get('message')
        token = data.get('token')
        
        if not message:
            emit('error', {'message': 'No message provided'})
            return
        
        # TODO: Validate JWT token from WebSocket
        
        if not model:
            emit('error', {'message': 'LLM not configured'})
            return
        
        # Generate response
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(message)
        
        # Stream response word by word
        words = response.text.split()
        for word in words:
            emit('chat_chunk', {'chunk': word + ' '})
            socketio.sleep(0.05)  # Simulate streaming
        
        emit('chat_complete', {'message': 'Response complete'})
        
    except Exception as e:
        emit('error', {'message': str(e)})

# ══════════════════════════════════════════════════════════════════════
# STATUS & INFO ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    """API documentation homepage"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Flask AI Agent API</title>
        <style>
            body {
                font-family: 'Segoe UI', system-ui, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 { margin-top: 0; font-size: 2.5em; }
            .endpoint {
                background: rgba(255, 255, 255, 0.15);
                padding: 20px;
                margin: 15px 0;
                border-radius: 10px;
            }
            .method {
                display: inline-block;
                padding: 5px 15px;
                background: #10b981;
                border-radius: 5px;
                font-weight: bold;
                margin-right: 10px;
            }
            code {
                background: rgba(0, 0, 0, 0.3);
                padding: 2px 8px;
                border-radius: 4px;
            }
            .feature {
                display: inline-block;
                background: rgba(255, 255, 255, 0.2);
                padding: 8px 16px;
                margin: 5px;
                border-radius: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Flask AI Agent API</h1>
            <p><strong>Status:</strong> 🟢 Online</p>
            
            <h2>✨ Features</h2>
            <div>
                <span class="feature">🔐 JWT Authentication</span>
                <span class="feature">💾 Database History</span>
                <span class="feature">⚡ WebSocket Streaming</span>
                <span class="feature">🎨 Markdown Responses</span>
                <span class="feature">🔑 API Keys</span>
            </div>
            
            <h2>📡 Endpoints</h2>
            
            <div class="endpoint">
                <span class="method">POST</span>
                <code>/api/auth/register</code>
                <p>Register a new user account</p>
            </div>
            
            <div class="endpoint">
                <span class="method">POST</span>
                <code>/api/auth/login</code>
                <p>Login and get JWT token</p>
            </div>
            
            <div class="endpoint">
                <span class="method">POST</span>
                <code>/api/chat</code>
                <p>Send message to AI agent (requires JWT)</p>
            </div>
            
            <div class="endpoint">
                <span class="method">GET</span>
                <code>/api/conversations</code>
                <p>Get user's conversation history</p>
            </div>
            
            <div class="endpoint">
                <span class="method">WebSocket</span>
                <code>ws://your-domain/socket.io</code>
                <p>Real-time chat streaming</p>
            </div>
            
            <h2>🚀 Quick Start</h2>
            <pre><code># Register
curl -X POST https://your-api.com/api/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"username":"user","email":"user@example.com","password":"pass123"}'

# Login
curl -X POST https://your-api.com/api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"user","password":"pass123"}'

# Chat
curl -X POST https://your-api.com/api/chat \\
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"message":"Hello AI!"}'</code></pre>
            
            <p style="margin-top: 30px; text-align: center;">
                <a href="/streamlit" style="background: #10b981; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold;">
                    Open Streamlit UI →
                </a>
            </p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/status', methods=['GET'])
def status():
    """API status check"""
    return jsonify({
        "status": "online",
        "llm_configured": model is not None,
        "agent_type": AGENT_TYPE,
        "features": ["auth", "database", "websocket", "markdown"],
        "timestamp": datetime.utcnow().isoformat()
    })

# ══════════════════════════════════════════════════════════════════════
# RUN APPLICATION
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('DEBUG', 'False') == 'True'
    )
 
 @ a p p . r o u t e ( ' / s t r e a m l i t ' ) 
 
 d e f   s t r e a m l i t _ r e d i r e c t ( ) : 
 
         " " " R e d i r e c t   t o   S t r e a m l i t   U I " " " 
 
         s t r e a m l i t _ u r l   =   o s . e n v i r o n . g e t ( ' S T R E A M L I T _ U R L ' ,   ' h t t p : / / l o c a l h o s t : 8 5 0 1 ' ) 
 
         r e t u r n   r e d i r e c t ( s t r e a m l i t _ u r l ) 
 
 