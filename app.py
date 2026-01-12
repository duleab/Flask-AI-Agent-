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
        port=7860,
        allow_unsafe_werkzeug=True,
        debug=False
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
  
 #   � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " �  
 #   C H A T   E N D P O I N T S  
 #   � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " � � " �  
  
 @ a p p . r o u t e ( ' / a p i / c h a t ' ,   m e t h o d s = [ ' P O S T ' ] )  
 d e f   c h a t ( ) :  
         " " " M a i n   c h a t   e n d p o i n t   w i t h   c o n v e r s a t i o n   h i s t o r y " " "  
         t r y :  
                 #   D e f a u l t   t o   g u e s t   u s e r  
                 u s e r   =   U s e r . q u e r y . f i l t e r _ b y ( u s e r n a m e = ' g u e s t ' ) . f i r s t ( )  
                 c u r r e n t _ u s e r _ i d   =   u s e r . i d  
                  
                 d a t a   =   r e q u e s t . g e t _ j s o n ( )  
                  
                 m e s s a g e   =   d a t a . g e t ( ' m e s s a g e ' )  
                 c o n v e r s a t i o n _ i d   =   d a t a . g e t ( ' c o n v e r s a t i o n _ i d ' )  
                  
                 i f   n o t   m e s s a g e :  
                         r e t u r n   j s o n i f y ( { " e r r o r " :   " M i s s i n g   m e s s a g e " } ) ,   4 0 0  
                  
                 i f   n o t   m o d e l :  
                         r e t u r n   j s o n i f y ( { " e r r o r " :   " L L M   n o t   c o n f i g u r e d " } ) ,   5 0 0  
                  
                 #   G e t   o r   c r e a t e   c o n v e r s a t i o n  
                 i f   c o n v e r s a t i o n _ i d :  
                         c o n v e r s a t i o n   =   C o n v e r s a t i o n . q u e r y . f i l t e r _ b y (  
                                 i d = c o n v e r s a t i o n _ i d ,  
                                 u s e r _ i d = c u r r e n t _ u s e r _ i d  
                         ) . f i r s t ( )  
                 e l s e :  
                         c o n v e r s a t i o n   =   C o n v e r s a t i o n (  
                                 u s e r _ i d = c u r r e n t _ u s e r _ i d ,  
                                 t i t l e = m e s s a g e [ : 5 0 ]   +   " . . . "   i f   l e n ( m e s s a g e )   >   5 0   e l s e   m e s s a g e  
                         )  
                         d b . s e s s i o n . a d d ( c o n v e r s a t i o n )  
                         d b . s e s s i o n . f l u s h ( )  
                  
                 #   G e t   c o n v e r s a t i o n   h i s t o r y  
                 m e s s a g e s   =   M e s s a g e . q u e r y . f i l t e r _ b y (  
                         c o n v e r s a t i o n _ i d = c o n v e r s a t i o n . i d  
                 ) . o r d e r _ b y ( M e s s a g e . t i m e s t a m p ) . a l l ( )  
                  
                 #   B u i l d   c h a t   h i s t o r y  
                 h i s t o r y   =   [ ]  
                 f o r   m s g   i n   m e s s a g e s :  
                         h i s t o r y . a p p e n d ( {  
                                 " r o l e " :   m s g . r o l e ,  
                                 " p a r t s " :   [ m s g . c o n t e n t ]  
                         } )  
                  
                 #   G e n e r a t e   r e s p o n s e  
                 c h a t _ s e s s i o n   =   m o d e l . s t a r t _ c h a t ( h i s t o r y = h i s t o r y )  
                 r e s p o n s e   =   c h a t _ s e s s i o n . s e n d _ m e s s a g e ( m e s s a g e )  
                 a i _ r e s p o n s e   =   r e s p o n s e . t e x t  
                  
                 #   S a v e   m e s s a g e s  
                 u s e r _ m s g   =   M e s s a g e (  
                         c o n v e r s a t i o n _ i d = c o n v e r s a t i o n . i d ,  
                         r o l e = ' u s e r ' ,  
                         c o n t e n t = m e s s a g e  
                 )  
                 a s s i s t a n t _ m s g   =   M e s s a g e (  
                         c o n v e r s a t i o n _ i d = c o n v e r s a t i o n . i d ,  
                         r o l e = ' a s s i s t a n t ' ,  
                         c o n t e n t = a i _ r e s p o n s e ,  
                         t o k e n s = l e n ( a i _ r e s p o n s e . s p l i t ( ) )  
                 )  
                  
                 d b . s e s s i o n . a d d ( u s e r _ m s g )  
                 d b . s e s s i o n . a d d ( a s s i s t a n t _ m s g )  
                 d b . s e s s i o n . c o m m i t ( )  
                  
                 #   C o n v e r t   t o   H T M L  
                 h t m l _ r e s p o n s e   =   m a r k d o w n . m a r k d o w n ( a i _ r e s p o n s e ,   e x t e n s i o n s = [ ' f e n c e d _ c o d e ' ,   ' t a b l e s ' ] )  
                  
                 r e t u r n   j s o n i f y ( {  
                         " r e s p o n s e " :   a i _ r e s p o n s e ,  
                         " h t m l " :   h t m l _ r e s p o n s e ,  
                         " c o n v e r s a t i o n _ i d " :   c o n v e r s a t i o n . i d ,  
                         " t i m e s t a m p " :   d a t e t i m e . u t c n o w ( ) . i s o f o r m a t ( )  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 d b . s e s s i o n . r o l l b a c k ( )  
                 r e t u r n   j s o n i f y ( { " e r r o r " :   s t r ( e ) } ) ,   5 0 0  
  
 @ a p p . r o u t e ( ' / a p i / c o n v e r s a t i o n s ' ,   m e t h o d s = [ ' G E T ' ] )  
 d e f   g e t _ c o n v e r s a t i o n s ( ) :  
         " " " G e t   u s e r ' s   c o n v e r s a t i o n   l i s t " " "  
         t r y :  
                 u s e r   =   U s e r . q u e r y . f i l t e r _ b y ( u s e r n a m e = ' g u e s t ' ) . f i r s t ( )  
                 c u r r e n t _ u s e r _ i d   =   u s e r . i d  
                  
                 c o n v e r s a t i o n s   =   C o n v e r s a t i o n . q u e r y . f i l t e r _ b y (  
                         u s e r _ i d = c u r r e n t _ u s e r _ i d  
                 ) . o r d e r _ b y ( C o n v e r s a t i o n . u p d a t e d _ a t . d e s c ( ) ) . a l l ( )  
                  
                 r e t u r n   j s o n i f y ( {  
                         " c o n v e r s a t i o n s " :   [ {  
                                 " i d " :   c . i d ,  
                                 " t i t l e " :   c . t i t l e ,  
                                 " c r e a t e d _ a t " :   c . c r e a t e d _ a t . i s o f o r m a t ( ) ,  
                                 " u p d a t e d _ a t " :   c . u p d a t e d _ a t . i s o f o r m a t ( ) ,  
                                 " m e s s a g e _ c o u n t " :   l e n ( c . m e s s a g e s )  
                         }   f o r   c   i n   c o n v e r s a t i o n s ]  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 r e t u r n   j s o n i f y ( { " e r r o r " :   s t r ( e ) } ) ,   5 0 0  
  
 @ a p p . r o u t e ( ' / a p i / c o n v e r s a t i o n s / < i n t : c o n v e r s a t i o n _ i d > ' ,   m e t h o d s = [ ' G E T ' ] )  
 d e f   g e t _ c o n v e r s a t i o n ( c o n v e r s a t i o n _ i d ) :  
         " " " G e t   s p e c i f i c   c o n v e r s a t i o n   w i t h   m e s s a g e s " " "  
         t r y :  
                 u s e r   =   U s e r . q u e r y . f i l t e r _ b y ( u s e r n a m e = ' g u e s t ' ) . f i r s t ( )  
                 c u r r e n t _ u s e r _ i d   =   u s e r . i d  
                  
                 c o n v e r s a t i o n   =   C o n v e r s a t i o n . q u e r y . f i l t e r _ b y (  
                         i d = c o n v e r s a t i o n _ i d ,  
                         u s e r _ i d = c u r r e n t _ u s e r _ i d  
                 ) . f i r s t ( )  
                  
                 i f   n o t   c o n v e r s a t i o n :  
                         r e t u r n   j s o n i f y ( { " e r r o r " :   " C o n v e r s a t i o n   n o t   f o u n d " } ) ,   4 0 4  
                  
                 m e s s a g e s   =   M e s s a g e . q u e r y . f i l t e r _ b y (  
                         c o n v e r s a t i o n _ i d = c o n v e r s a t i o n _ i d  
                 ) . o r d e r _ b y ( M e s s a g e . t i m e s t a m p ) . a l l ( )  
                  
                 r e t u r n   j s o n i f y ( {  
                         " c o n v e r s a t i o n " :   {  
                                 " i d " :   c o n v e r s a t i o n . i d ,  
                                 " t i t l e " :   c o n v e r s a t i o n . t i t l e ,  
                                 " c r e a t e d _ a t " :   c o n v e r s a t i o n . c r e a t e d _ a t . i s o f o r m a t ( )  
                         } ,  
                         " m e s s a g e s " :   [ {  
                                 " r o l e " :   m . r o l e ,  
                                 " c o n t e n t " :   m . c o n t e n t ,  
                                 " t i m e s t a m p " :   m . t i m e s t a m p . i s o f o r m a t ( )  
                         }   f o r   m   i n   m e s s a g e s ]  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 r e t u r n   j s o n i f y ( { " e r r o r " :   s t r ( e ) } ) ,   5 0 0  
 