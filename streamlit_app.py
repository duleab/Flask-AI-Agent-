# ╔════════════════════════════════════════════════════════════════════╗
# ║                streamlit_app.py - Beautiful Frontend UI            ║
# ║              Connects to Flask API • Real-time chat                ║
# ╚════════════════════════════════════════════════════════════════════╝

import streamlit as st
import requests
import json
from datetime import datetime
import os

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

API_BASE_URL = os.environ.get('API_URL', 'http://localhost:5000')

# Page config
st.set_page_config(
    page_title="AI Agent Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    .stChatMessage {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 15px;
        margin: 10px 0;
    }
    .stTextInput input {
        border-radius: 20px;
        border: 2px solid rgba(255, 255, 255, 0.3);
        background: rgba(255, 255, 255, 0.1);
        color: white;
    }
    .stButton button {
        border-radius: 20px;
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        border: none;
        padding: 10px 30px;
        font-weight: bold;
    }
    h1, h2, h3 {
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALIZATION
# ══════════════════════════════════════════════════════════════════════

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'conversations' not in st.session_state:
    st.session_state.conversations = []
if 'current_conversation_id' not in st.session_state:
    st.session_state.current_conversation_id = None

# ══════════════════════════════════════════════════════════════════════
# API FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def register_user(username, email, password):
    """Register new user"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/auth/register",
            json={"username": username, "email": email, "password": password}
        )
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def login_user(username, password):
    """Login user"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json={"username": username, "password": password}
        )
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def send_message(message, token, conversation_id=None):
    """Send message to API"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        if conversation_id:
            data["conversation_id"] = conversation_id
        
        response = requests.post(
            f"{API_BASE_URL}/api/chat",
            headers=headers,
            json=data
        )
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def get_conversations(token):
    """Get user's conversations"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE_URL}/api/conversations",
            headers=headers
        )
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def load_conversation(conversation_id, token):
    """Load specific conversation"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{API_BASE_URL}/api/conversations/{conversation_id}",
            headers=headers
        )
        return response.json(), response.status_code
    except Exception as e:
        return {"error": str(e)}, 500

# ══════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ══════════════════════════════════════════════════════════════════════

def show_auth_page():
    """Show login/register page"""
    
    st.title("🤖 AI Agent Platform")
    st.markdown("### Welcome! Please login or create an account")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login to your account")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                if not username or not password:
                    st.error("Please fill in all fields")
                else:
                    with st.spinner("Logging in..."):
                        result, status = login_user(username, password)
                        
                        if status == 200:
                            st.session_state.logged_in = True
                            st.session_state.access_token = result['access_token']
                            st.session_state.username = result['username']
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error(result.get('error', 'Login failed'))
    
    with tab2:
        st.subheader("Create a new account")
        with st.form("register_form"):
            new_username = st.text_input("Username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            register = st.form_submit_button("Register")
            
            if register:
                if not all([new_username, new_email, new_password, confirm_password]):
                    st.error("Please fill in all fields")
                elif new_password != confirm_password:
                    st.error("Passwords don't match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    with st.spinner("Creating account..."):
                        result, status = register_user(new_username, new_email, new_password)
                        
                        if status == 201:
                            st.session_state.logged_in = True
                            st.session_state.access_token = result['access_token']
                            st.session_state.username = new_username
                            st.success("Account created! Logging you in...")
                            st.rerun()
                        else:
                            st.error(result.get('error', 'Registration failed'))

# ══════════════════════════════════════════════════════════════════════
# MAIN CHAT PAGE
# ══════════════════════════════════════════════════════════════════════

def show_chat_page():
    """Show main chat interface"""
    
    # Sidebar
    with st.sidebar:
        st.title("💬 Conversations")
        
        # User info
        st.markdown(f"**User:** {st.session_state.username}")
        
        if st.button("🔄 Refresh Conversations"):
            result, status = get_conversations(st.session_state.access_token)
            if status == 200:
                st.session_state.conversations = result.get('conversations', [])
        
        # New conversation
        if st.button("➕ New Conversation", use_container_width=True):
            st.session_state.current_conversation_id = None
            st.session_state.messages = []
            st.rerun()
        
        # Load conversations on first run
        if not st.session_state.conversations:
            result, status = get_conversations(st.session_state.access_token)
            if status == 200:
                st.session_state.conversations = result.get('conversations', [])
        
        # Display conversations
        st.markdown("---")
        for conv in st.session_state.conversations:
            if st.button(
                f"📝 {conv['title'][:30]}...",
                key=f"conv_{conv['id']}",
                use_container_width=True
            ):
                # Load conversation
                result, status = load_conversation(conv['id'], st.session_state.access_token)
                if status == 200:
                    st.session_state.current_conversation_id = conv['id']
                    st.session_state.messages = result['messages']
                    st.rerun()
        
        st.markdown("---")
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.session_state.access_token = None
            st.session_state.username = None
            st.session_state.messages = []
            st.rerun()
    
    # Main chat area
    st.title("🤖 AI Agent Chat")
    
    # Display messages
    for message in st.session_state.messages:
        role = message['role']
        content = message['content']
        
        with st.chat_message(role):
            st.markdown(content)
    
    # Chat input
    if prompt := st.chat_input("Type your message here..."):
        # Add user message to UI
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result, status = send_message(
                    prompt,
                    st.session_state.access_token,
                    st.session_state.current_conversation_id
                )
                
                if status == 200:
                    response = result['response']
                    st.markdown(response)
                    
                    # Update conversation ID
                    if not st.session_state.current_conversation_id:
                        st.session_state.current_conversation_id = result.get('conversation_id')
                    
                    # Add to messages
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                else:
                    error_msg = result.get('error', 'Failed to get response')
                    st.error(f"Error: {error_msg}")

# ══════════════════════════════════════════════════════════════════════
# MAIN APP LOGIC
# ══════════════════════════════════════════════════════════════════════

def main():
    """Main application logic"""
    
    if not st.session_state.logged_in:
        show_auth_page()
    else:
        show_chat_page()

if __name__ == "__main__":
    main()