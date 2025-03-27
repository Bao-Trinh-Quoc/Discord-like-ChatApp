import secrets
import time
from datetime import datetime, timedelta

from database import db
from logger import system_logger

class Authentication:
    def __init__(self):
        self.active_sessions = {}  # token -> username mapping
        self.session_timeout = 3600  # 1 hour in seconds
    
    def register_user(self, username, password, email=None):
        """Register a new user (simplified for testing)"""
        # Check if username already exists
        if db.get_user(username):
            return False, "Username already exists"
        
        # For testing purposes, store password directly without hashing
        stored_password = password
        
        # Add user to database
        success = db.add_user(username, stored_password, email)
        if success:
            system_logger.log_auth(username, True, "registration")
            return True, "User registered successfully"
        
        return False, "Failed to register user"
    
    def login(self, username, password, ip_address):
        """Authenticate a user and create a session (simplified for testing)"""
        user = db.get_user(username)
        if not user:
            system_logger.log_auth(username, False, ip_address)
            return False, "Invalid username or password", None
        
        # Simple password check (plaintext for testing)
        if password != user["password_hash"]:
            system_logger.log_auth(username, False, ip_address)
            return False, "Invalid username or password", None
        
        # Create session token
        token = secrets.token_hex(32)
        expires = datetime.now() + timedelta(seconds=self.session_timeout)
        
        self.active_sessions[token] = {
            "username": username,
            "expires": expires,
            "ip_address": ip_address
        }
        
        # Update user status to online
        db.update_user_status(username, "online")
        
        system_logger.log_auth(username, True, ip_address)
        return True, "Login successful", token
    
    def login_visitor(self, visitor_name, ip_address):
        """Create a visitor session (no authentication required)"""
        # Create session token for visitor
        token = secrets.token_hex(32)
        expires = datetime.now() + timedelta(seconds=self.session_timeout)
        
        self.active_sessions[token] = {
            "username": f"visitor:{visitor_name}",
            "expires": expires,
            "ip_address": ip_address,
            "visitor": True
        }
        
        system_logger.log_auth(f"visitor:{visitor_name}", True, ip_address)
        return True, "Visitor session created", token
    
    def validate_session(self, token):
        """Check if a session is valid and not expired"""
        if token not in self.active_sessions:
            return False, "Invalid session", None
        
        session = self.active_sessions[token]
        
        # Check if expired
        if datetime.now() > session["expires"]:
            # Clean up expired session
            del self.active_sessions[token]
            return False, "Session expired", None
        
        # Extend session timeout
        session["expires"] = datetime.now() + timedelta(seconds=self.session_timeout)
        
        return True, "Session valid", session["username"]
    
    def logout(self, token):
        """End a user session"""
        if token in self.active_sessions:
            username = self.active_sessions[token]["username"]
            
            # If not a visitor, update status to offline
            if not username.startswith("visitor:"):
                db.update_user_status(username, "offline")
            
            # Remove session
            del self.active_sessions[token]
            
            return True, "Logged out successfully"
        
        return False, "Invalid session"
    
    def set_user_status(self, token, status):
        """Set user status (online, offline, invisible)"""
        valid, msg, username = self.validate_session(token)
        if not valid or username.startswith("visitor:"):
            return False, "Invalid session or visitor account"
        
        if status not in ["online", "offline", "invisible"]:
            return False, "Invalid status value"
        
        success = db.update_user_status(username, status)
        if success:
            return True, f"Status updated to {status}"
        
        return False, "Failed to update status"
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        current_time = datetime.now()
        expired_tokens = []
        
        for token, session in self.active_sessions.items():
            if current_time > session["expires"]:
                expired_tokens.append(token)
                
                # Update user status if needed
                username = session["username"]
                if not username.startswith("visitor:"):
                    db.update_user_status(username, "offline")
        
        # Remove expired sessions
        for token in expired_tokens:
            del self.active_sessions[token]
        
        return len(expired_tokens)

# Singleton instance
auth = Authentication()