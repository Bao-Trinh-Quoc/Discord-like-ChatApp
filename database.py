import json
import os
import time
from datetime import datetime

class Database:
    def __init__(self, db_dir="database"):
        self.db_dir = db_dir
        self.users_file = f"{db_dir}/users.json"
        self.channels_file = f"{db_dir}/channels.json"
        self.messages_dir = f"{db_dir}/messages"
        self.peers_file = f"{db_dir}/peers.json"
        self._initialize_db()
        
        # Comment out stream tracking for now
        # self.streams = {}  # channel -> {streamer, viewers, start_time}
    
    def _initialize_db(self):
        """Initialize database structure if it doesn't exist"""
        # Create main database directory
        if not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir)
        
        # Create messages directory
        if not os.path.exists(self.messages_dir):
            os.makedirs(self.messages_dir)
        
        # Initialize users file
        if not os.path.exists(self.users_file):
            self._save_json(self.users_file, {})
        
        # Initialize channels file
        if not os.path.exists(self.channels_file):
            self._save_json(self.channels_file, {})
        
        # Initialize peers file
        if not os.path.exists(self.peers_file):
            self._save_json(self.peers_file, {})
    
    def _load_json(self, file_path):
        """Load data from a JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _save_json(self, file_path, data):
        """Save data to a JSON file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    # User management
    def add_user(self, username, password_hash, email=None):
        """Add a new user to the database"""
        users = self._load_json(self.users_file)
        if username in users:
            return False
        
        users[username] = {
            "password_hash": password_hash,
            "email": email,
            "created_at": datetime.now().isoformat(),
            "status": "offline",
            "channels_owned": [],
            "channels_joined": []
        }
        self._save_json(self.users_file, users)
        return True
    
    def authenticate_user(self, username, password_hash):
        """Check if username and password match"""
        users = self._load_json(self.users_file)
        if username in users and users[username]["password_hash"] == password_hash:
            return True
        return False
    
    def update_user_status(self, username, status):
        """Update user's online status (online, offline, invisible)"""
        users = self._load_json(self.users_file)
        if username in users:
            users[username]["status"] = status
            self._save_json(self.users_file, users)
            return True
        return False
    
    def get_user(self, username):
        """Get user details"""
        users = self._load_json(self.users_file)
        return users.get(username)
    
    def get_online_users(self):
        """Get list of users with 'online' status"""
        users = self._load_json(self.users_file)
        return {username: user for username, user in users.items() 
                if user["status"] == "online"}
    
    # Channel management
    def create_channel(self, channel_name, owner, description=""):
        """Create a new channel"""
        channels = self._load_json(self.channels_file)
        if channel_name in channels:
            return False
        
        channels[channel_name] = {
            "owner": owner,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "members": [owner],
            "last_message_id": 0
        }
        self._save_json(self.channels_file, channels)
        
        # Update user's owned channels
        users = self._load_json(self.users_file)
        if owner in users:
            if "channels_owned" not in users[owner]:
                users[owner]["channels_owned"] = []
            users[owner]["channels_owned"].append(channel_name)
            self._save_json(self.users_file, users)
        
        # Create message file for this channel
        channel_msgs_file = f"{self.messages_dir}/{channel_name}.json"
        self._save_json(channel_msgs_file, {})
        
        return True
    
    def join_channel(self, channel_name, username):
        """Add a user to a channel"""
        channels = self._load_json(self.channels_file)
        if channel_name not in channels:
            return False
        
        if username not in channels[channel_name]["members"]:
            channels[channel_name]["members"].append(username)
            self._save_json(self.channels_file, channels)
        
        # Update user's joined channels
        users = self._load_json(self.users_file)
        if username in users:
            if "channels_joined" not in users[username]:
                users[username]["channels_joined"] = []
            if channel_name not in users[username]["channels_joined"]:
                users[username]["channels_joined"].append(channel_name)
                self._save_json(self.users_file, users)
        
        return True
    
    def get_channel(self, channel_name):
        """Get channel information"""
        channels = self._load_json(self.channels_file)
        if channel_name in channels:
            channel = channels[channel_name]
            return {
                "name": channel_name,
                "owner": channel["owner"],
                "description": channel.get("description", ""),
                "created_at": channel["created_at"],
                "members": channel.get("members", [])
            }
        return None
    
    def list_channels(self):
        """List all available channels"""
        channels = self._load_json(self.channels_file)
        return channels if channels else {}
    
    def get_user_channels(self, username):
        """Get channels a user has joined"""
        users = self._load_json(self.users_file)
        if username in users:
            return users[username].get("channels_joined", [])
        return []
    
    # Message management
    def add_message(self, channel_name, username, content):
        """Add a message to a channel"""
        channels = self._load_json(self.channels_file)
        if channel_name not in channels:
            return None
        
        # Load channel messages
        channel_msgs_file = f"{self.messages_dir}/{channel_name}.json"
        messages = self._load_json(channel_msgs_file)
        
        # Increment message ID
        msg_id = channels[channel_name]["last_message_id"] + 1
        channels[channel_name]["last_message_id"] = msg_id
        self._save_json(self.channels_file, channels)
        
        # Create message
        timestamp = datetime.now().isoformat()
        message = {
            "id": msg_id,
            "username": username,
            "content": content,
            "timestamp": timestamp
        }
        
        # Save message
        messages[str(msg_id)] = message
        self._save_json(channel_msgs_file, messages)
        
        return msg_id
    
    def get_messages(self, channel_name, since_id=0, limit=50):
        """Get messages from a channel, optionally after a certain ID"""
        channel_msgs_file = f"{self.messages_dir}/{channel_name}.json"
        
        try:
            # Load messages
            messages = self._load_json(channel_msgs_file)
            if not messages:
                return []

            # Convert messages to a list and ensure all fields are properly formatted
            messages_list = []
            for msg_id, msg in messages.items():
                try:
                    # Convert id to int and ensure all required fields exist
                    msg_obj = {
                        "id": int(msg_id),
                        "username": str(msg.get("username", "")),
                        "content": str(msg.get("content", "")),
                        "timestamp": str(msg.get("timestamp", ""))
                    }
                    messages_list.append(msg_obj)
                except (ValueError, TypeError) as e:
                    print(f"Error processing message {msg_id}: {e}")
                    continue

            # Sort by ID
            messages_list.sort(key=lambda x: x["id"])

            # Filter messages after since_id
            filtered_msgs = [msg for msg in messages_list if msg["id"] > since_id]

            # Apply limit if specified
            if limit > 0:
                filtered_msgs = filtered_msgs[-limit:]

            return filtered_msgs

        except Exception as e:
            print(f"Error getting messages from {channel_msgs_file}: {e}")
            return []
    
    # Peer tracking
    def register_peer(self, username, ip, port, peer_type="normal"):
        """Register a peer in the system"""
        peers = self._load_json(self.peers_file)
        
        peer_id = f"{username}:{ip}:{port}"
        peers[peer_id] = {
            "username": username,
            "ip": ip,
            "port": port,
            "type": peer_type,  # normal, visitor, etc.
            "last_seen": datetime.now().isoformat(),
            "hosting_channels": []
        }
        self._save_json(self.peers_file, peers)
        return peer_id
    
    def update_peer(self, peer_id, **kwargs):
        """Update peer information"""
        peers = self._load_json(self.peers_file)
        if peer_id not in peers:
            return False
        
        for key, value in kwargs.items():
            if key in peers[peer_id]:
                peers[peer_id][key] = value
        
        peers[peer_id]["last_seen"] = datetime.now().isoformat()
        self._save_json(self.peers_file, peers)
        return True
    
    def get_active_peers(self, max_age_seconds=300):
        """Get active peers (seen within the time window)"""
        peers = self._load_json(self.peers_file)
        now = datetime.now()
        active_peers = {}
        
        for peer_id, peer_info in peers.items():
            last_seen = datetime.fromisoformat(peer_info["last_seen"])
            age_seconds = (now - last_seen).total_seconds()
            
            if age_seconds <= max_age_seconds:
                active_peers[peer_id] = peer_info
        
        return active_peers
    
    def get_channel_host(self, channel_name):
        """Find the peer hosting a specific channel"""
        peers = self._load_json(self.peers_file)
        
        for peer_id, peer_info in peers.items():
            if channel_name in peer_info.get("hosting_channels", []):
                return peer_info
        
        return None
    
    def remove_peer(self, peer_id):
        """Remove a peer from the active peers list"""
        peers = self._load_json(self.peers_file)
        if peer_id in peers:
            del peers[peer_id]
            self._save_json(self.peers_file, peers)
            return True
        return False
    
    # Stream management - commented out for now to focus on messaging
    '''
    def start_stream(self, channel, username):
        """Start a new stream in a channel"""
        if channel not in self.channels:
            return False
            
        if channel in self.streams:
            return False  # Already streaming
            
        self.streams[channel] = {
            "streamer": username,
            "viewers": set(),
            "start_time": datetime.now().isoformat()
        }
        return True
    
    def end_stream(self, channel):
        """End a stream in a channel"""
        if channel in self.streams:
            del self.streams[channel]
            return True
        return False
    
    def add_stream_viewer(self, channel, username):
        """Add a viewer to a stream"""
        if channel not in self.streams:
            return False
            
        self.streams[channel]["viewers"].add(username)
        return True
    
    def remove_stream_viewer(self, channel, username):
        """Remove a viewer from a stream"""
        if channel not in self.streams:
            return False
            
        self.streams[channel]["viewers"].discard(username)
        return True
    
    def get_stream_info(self, channel):
        """Get information about a channel's stream"""
        return self.streams.get(channel)
    
    def get_active_streams(self):
        """Get all active streams"""
        return self.streams
    '''

# Singleton instance
db = Database()