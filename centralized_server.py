import socket
import threading
import json
import time
import argparse
from datetime import datetime
import os

from database import db
from logger import system_logger
from authentication import auth

# Protocol constants
MSG_REGISTER = "REGISTER"
MSG_HEARTBEAT = "HEARTBEAT"
MSG_GET_PEERS = "GET_PEERS"
MSG_CHANNEL_HOST = "CHANNEL_HOST"
MSG_SYNC_DATA = "SYNC_DATA"
MSG_AUTH = "AUTH"
MSG_VISITOR = "VISITOR"
MSG_LOGOUT = "LOGOUT"
MSG_ERROR = "ERROR"
MSG_SUCCESS = "SUCCESS"
MSG_JOIN_CHANNEL = "JOIN_CHANNEL"
MSG_GET_HISTORY = "GET_HISTORY"
MSG_SEND_MESSAGE = "SEND_MESSAGE"
MSG_STATUS = "STATUS"  # Added status message type
MSG_GET_ONLINE_USERS = "GET_ONLINE_USERS"  # Added new message type
MSG_STREAM_START = "STREAM_START"
MSG_STREAM_END = "STREAM_END"
MSG_STREAM_JOIN = "STREAM_JOIN"
MSG_STREAM_LEAVE = "STREAM_LEAVE"
MSG_GET_STREAM_INFO = "GET_STREAM_INFO"
MSG_STREAM_MESSAGE = "STREAM_MESSAGE"
MSG_GET_STREAM_MESSAGES = "GET_STREAM_MESSAGES"
MSG_GET_NOTIFICATIONS = "GET_NOTIFICATIONS"  # Add notification message types
MSG_MARK_NOTIFICATIONS_READ = "MARK_NOTIFICATIONS_READ"

class CentralServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None
        self.clients = {}  # Maps client address to client data
        self.active_streams = {}  # channel -> {streamer, viewers, start_time}
        self.stream_messages = {}  # channel -> list of messages
        self.last_message_id = 0  # Global message ID counter
        self.stream_messages_dir = os.path.join("database", "stream_messages")  # Directory to store stream messages
        
        # Add notification tracking
        self.notifications = {}  # username -> list of notifications
        self.last_notification_id = 0  # Global notification ID counter
        
        # Create database and stream messages directories if they don't exist
        if not os.path.exists("database"):
            os.makedirs("database")
        if not os.path.exists(self.stream_messages_dir):
            os.makedirs(self.stream_messages_dir)
        
        # Load any existing stream messages
        self._load_stream_messages()
        
        # Cleanup thread for expired sessions and inactive peers
        self.cleanup_thread = threading.Thread(target=self._cleanup_routine)
        self.cleanup_thread.daemon = True
    
    def start(self):
        """Start the central server"""
        try:
            # Create socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            
            print(f"Central server is listening on {self.host}:{self.port}")
            system_logger.log_connection(self.host, self.port, "0.0.0.0", 0, "server_started")
            
            self.running = True
            self.cleanup_thread.start()
            
            # Main server loop
            while self.running:
                try:
                    # Accept client connection
                    client_socket, client_addr = self.server_socket.accept()
                    
                    # Start a new thread to handle the client
                    client_handler = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_addr)
                    )
                    client_handler.daemon = True
                    client_handler.start()
                    
                except Exception as e:
                    print(f"Error accepting connection: {e}")
            
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
    
    def _handle_client(self, client_socket, client_addr):
        """Handle client connection"""
        ip, port = client_addr
        client_info = {"ip": ip, "port": port, "socket": client_socket}
        
        system_logger.log_connection(ip, port, self.host, self.port, "client_connected")
        response = {"success": False, "message": "Unknown request type"}
        
        try:
            # Receive data from client
            data = b""
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                try:
                    # Try to decode and parse the accumulated data
                    request = json.loads(data.decode('utf-8'))
                    break  # If successful, exit the loop
                except json.JSONDecodeError:
                    continue  # If incomplete, continue receiving
                    
            if not data:
                return
                
            message_type = request.get("type")
            print(f"Received request type: {message_type}")  # Debug print
            
            # Process the request based on its type
            if message_type == MSG_STREAM_MESSAGE:
                response = self._handle_stream_message(request, client_info)
            elif message_type == MSG_GET_STREAM_MESSAGES:
                response = self._handle_get_stream_messages(request, client_info)
            elif message_type == MSG_REGISTER:
                response = self._handle_register(request, client_info)
            elif message_type == MSG_HEARTBEAT:
                response = self._handle_heartbeat(request, client_info)
            elif message_type == MSG_GET_PEERS:
                response = self._handle_get_peers(request, client_info)
            elif message_type == MSG_CHANNEL_HOST:
                response = self._handle_channel_host(request, client_info)
            elif message_type == MSG_SYNC_DATA:
                response = self._handle_sync_data(request, client_info)
            elif message_type == MSG_AUTH:
                response = self._handle_auth(request, client_info)
            elif message_type == MSG_VISITOR:
                response = self._handle_visitor(request, client_info)
            elif message_type == MSG_LOGOUT:
                response = self._handle_logout(request, client_info)
            elif message_type == MSG_JOIN_CHANNEL:
                response = self._handle_join_channel(request, client_info)
            elif message_type == MSG_GET_HISTORY:
                response = self._handle_get_history(request, client_info)
            elif message_type == MSG_SEND_MESSAGE:
                response = self._handle_send_message(request, client_info)
            elif message_type == MSG_STATUS:
                response = self._handle_status(request, client_info)
            elif message_type == MSG_GET_ONLINE_USERS:
                response = self._handle_get_online_users(request, client_info)
            elif message_type == MSG_STREAM_START:
                response = self._handle_stream_start(request, client_info)
            elif message_type == MSG_STREAM_END:
                response = self._handle_stream_end(request, client_info)
            elif message_type == MSG_STREAM_JOIN:
                response = self._handle_stream_join(request, client_info)
            elif message_type == MSG_STREAM_LEAVE:
                response = self._handle_stream_leave(request, client_info)
            elif message_type == MSG_GET_STREAM_INFO:
                response = self._handle_get_stream_info(request, client_info)
            elif message_type == MSG_GET_NOTIFICATIONS:
                response = self._handle_get_notifications(request, client_info)
            elif message_type == MSG_MARK_NOTIFICATIONS_READ:
                response = self._handle_mark_notifications_read(request, client_info)

            # Send response
            response_data = json.dumps(response).encode('utf-8')
            client_socket.sendall(response_data)
            
        except Exception as e:
            print(f"Error handling client {client_addr}: {e}")
            response = {
                "success": False,
                "type": MSG_ERROR,
                "message": str(e)
            }
            try:
                client_socket.sendall(json.dumps(response).encode('utf-8'))
            except:
                pass
                
        finally:
            # Log data transfer
            system_logger.log_data_transfer(
                self.host, self.port, ip, port, 
                len(json.dumps(response).encode('utf-8')), 
                "sent"
            )
            client_socket.close()
    
    def _handle_register(self, request, client_info):
        """Handle peer registration"""
        token = request.get("token")
        peer_port = request.get("port")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Determine if this is a visitor
        is_visitor = username.startswith("visitor:")
        peer_type = "visitor" if is_visitor else "normal"
        username_clean = username.replace("visitor:", "") if is_visitor else username
        
        # Register peer
        peer_ip = client_info["ip"]
        peer_id = db.register_peer(username_clean, peer_ip, peer_port, peer_type)
        
        system_logger.log_connection(
            peer_ip, peer_port, self.host, self.port, 
            f"peer_registered:{username_clean}"
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Registered successfully",
            "peer_id": peer_id
        }
    
    def _handle_heartbeat(self, request, client_info):
        """Handle peer heartbeat updates"""
        peer_id = request.get("peer_id")
        hosting_channels = request.get("hosting_channels", [])
        
        # Update peer's last seen time and hosting channels
        success = db.update_peer(peer_id, hosting_channels=hosting_channels)
        
        if success:
            return {
                "success": True,
                "type": MSG_SUCCESS,
                "message": "Heartbeat acknowledged"
            }
        else:
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": "Invalid peer ID"
            }
    
    def _handle_get_peers(self, request, client_info):
        """Handle request for list of active peers"""
        token = request.get("token")
        channel_name = request.get("channel")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Get active peers
        active_peers = db.get_active_peers()
        
        # If channel specified, filter for peers that host that channel
        if channel_name:
            host = db.get_channel_host(channel_name)
            if host:
                return {
                    "success": True,
                    "type": MSG_SUCCESS,
                    "host": host
                }
            else:
                return {
                    "success": False, 
                    "type": MSG_ERROR,
                    "message": f"No host found for channel {channel_name}"
                }
        
        # Filter out sensitive info before sending
        filtered_peers = {}
        for pid, peer in active_peers.items():
            filtered_peers[pid] = {
                "username": peer["username"],
                "ip": peer["ip"],
                "port": peer["port"],
                "type": peer["type"],
                "hosting_channels": peer.get("hosting_channels", [])
            }
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "peers": filtered_peers
        }
    
    def _handle_channel_host(self, request, client_info):
        """Handle request to become channel host"""
        token = request.get("token")
        channel_name = request.get("channel")
        action = request.get("action", "host")  # host or release
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if visitor (who can't host)
        if username.startswith("visitor:"):
            return {"success": False, "type": MSG_ERROR, "message": "Visitors cannot host channels"}
        
        # Get peer information
        peer_ip = client_info["ip"]
        peer_port = request.get("port")
        peer_id = f"{username}:{peer_ip}:{peer_port}"
        
        # Get channel info
        channel = db.get_channel(channel_name)
        if not channel:
            return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}
        
        # Check if this user owns the channel
        if channel["owner"] != username:
            return {"success": False, "type": MSG_ERROR, "message": "Only channel owner can host"}
        
        # Update peer information
        peer = db.get_active_peers().get(peer_id)
        if not peer:
            return {"success": False, "type": MSG_ERROR, "message": "Peer not registered"}
        
        hosting_channels = peer.get("hosting_channels", [])
        
        if action == "host" and channel_name not in hosting_channels:
            hosting_channels.append(channel_name)
        elif action == "release" and channel_name in hosting_channels:
            hosting_channels.remove(channel_name)
        
        db.update_peer(peer_id, hosting_channels=hosting_channels)
        
        system_logger.log_channel_event(
            channel_name, 
            f"{'hosting' if action == 'host' else 'released'}", 
            username
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Channel {channel_name} {'hosted' if action == 'host' else 'released'} successfully"
        }
    
    def _handle_sync_data(self, request, client_info):
        """Handle channel data synchronization"""
        token = request.get("token")
        channel_name = request.get("channel")
        messages = request.get("messages", [])
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if visitor (who can't sync data)
        if username.startswith("visitor:"):
            return {"success": False, "type": MSG_ERROR, "message": "Visitors cannot sync data"}
        
        # Get channel info
        channel = db.get_channel(channel_name)
        if not channel:
            return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}
        
        # Check if this user owns the channel
        if channel["owner"] != username:
            return {"success": False, "type": MSG_ERROR, "message": "Only channel owner can sync data"}
        
        # Process messages (this is simplified - real implementation would be more complex)
        for msg in messages:
            db.add_message(channel_name, msg["username"], msg["content"])
        
        system_logger.log_channel_event(
            channel_name, 
            f"data_synced with {len(messages)} messages", 
            username
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Synchronized {len(messages)} messages for channel {channel_name}"
        }
    
    def _handle_auth(self, request, client_info):
        """Handle authentication requests"""
        username = request.get("username")
        password = request.get("password")
        
        # Authenticate user
        success, message, token = auth.login(username, password, client_info["ip"])
        
        return {
            "success": success,
            "type": MSG_SUCCESS if success else MSG_ERROR,
            "message": message,
            "token": token
        }
    
    def _handle_visitor(self, request, client_info):
        """Handle visitor login"""
        visitor_name = request.get("name")
        
        # Create visitor session
        success, message, token = auth.login_visitor(visitor_name, client_info["ip"])
        
        return {
            "success": success,
            "type": MSG_SUCCESS if success else MSG_ERROR,
            "message": message,
            "token": token
        }
    
    def _handle_logout(self, request, client_info):
        """Handle logout requests"""
        token = request.get("token")
        
        # End session
        success, message = auth.logout(token)
        
        return {
            "success": success,
            "type": MSG_SUCCESS if success else MSG_ERROR,
            "message": message
        }
    
    def _handle_join_channel(self, request, client_info):
        """Handle request to join a channel through the central server"""
        token = request.get("token")
        channel_name = request.get("channel")

        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}

        # Check if the channel exists
        channel = db.get_channel(channel_name)
        if not channel:
            return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}

        # Add user to the channel's member list if not already present
        if username not in channel["members"]:
            db.join_channel(channel_name, username)

        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Joined channel {channel_name} via central server",
            "channel": channel
        }
    
    def _handle_get_history(self, request, client_info):
        """Handle request to get channel message history"""
        token = request.get("token")
        channel_name = request.get("channel")
        since_id = request.get("since_id", 0)
        limit = request.get("limit", 50)

        try:
            # Validate session
            valid, msg, username = auth.validate_session(token)
            if not valid:
                return {"success": False, "type": MSG_ERROR, "message": msg}

            # Check if channel exists
            channel = db.get_channel(channel_name)
            if not channel:
                return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}

            # Get messages from database
            messages = db.get_messages(channel_name, since_id, limit)

            # Ensure messages are JSON-serializable
            clean_messages = []
            for msg in messages:
                clean_msg = {
                    "id": msg["id"],
                    "username": str(msg["username"]),
                    "content": str(msg["content"]),
                    "timestamp": str(msg["timestamp"])
                }
                clean_messages.append(clean_msg)

            # Create response with clean messages
            response = {
                "success": True,
                "type": MSG_SUCCESS,
                "messages": clean_messages
            }

            # Validate that the response can be JSON serialized
            json.dumps(response)
            return response

        except Exception as e:
            print(f"Error in _handle_get_history: {str(e)}")
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": "Internal server error processing messages"
            }

    def _handle_send_message(self, request, client_info):
        """Handle request to send a message to a channel"""
        token = request.get("token")
        channel_name = request.get("channel")
        content = request.get("content")

        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}

        # Check if channel exists
        channel = db.get_channel(channel_name)
        if not channel:
            return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}

        # Check if user is a member of the channel
        if username not in channel["members"]:
            return {"success": False, "type": MSG_ERROR, "message": "You are not a member of this channel"}

        # Add message to database
        msg_id = db.add_message(channel_name, username, content)
        if msg_id:
            system_logger.log_channel_event(channel_name, f"Message sent by {username}", username)
            
            # Get online users
            online_users = db.get_online_users()
            print(f"Online users: {list(online_users.keys())}")  # Debug print
            
            # Add notifications for channel members who are online (except sender)
            for member in channel["members"]:
                if member != username and member in online_users:
                    print(f"Adding notification for online channel member: {member}")  # Debug print
                    self._add_notification(
                        member,
                        "new_message",
                        f"New message from {username} in {channel_name}",
                        channel_name
                    )
            
            return {
                "success": True,
                "type": MSG_SUCCESS,
                "message": "Message sent successfully",
                "message_id": msg_id
            }
        else:
            return {"success": False, "type": MSG_ERROR, "message": "Failed to send message"}
    
    def _handle_status(self, request, client_info):
        """Handle status change requests"""
        token = request.get("token")
        status = request.get("status")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if visitor (who can't change status)
        if username.startswith("visitor:"):
            return {"success": False, "type": MSG_ERROR, "message": "Visitors cannot change status"}
        
        # Check if valid status
        if status not in ["online", "offline", "invisible"]:
            return {"success": False, "type": MSG_ERROR, "message": "Invalid status value"}
        
        # Update user status
        success = db.update_user_status(username, status)
        
        if success:
            system_logger.log_auth(username, True, f"status_change:{status}")
            return {
                "success": True,
                "type": MSG_SUCCESS,
                "message": f"Status updated to {status}"
            }
        else:
            return {
                "success": False, 
                "type": MSG_ERROR,
                "message": "Failed to update status"
            }
    
    def _handle_get_online_users(self, request, client_info):
        """Handle request to get online users"""
        token = request.get("token")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Get online users
        online_users = db.get_online_users()
        
        # Format the user data for the response
        users_list = []
        for username, user_data in online_users.items():
            # Don't include sensitive data
            users_list.append({
                "username": username,
                "status": user_data.get("status", "online")
            })
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "users": users_list
        }
    
    def _handle_stream_start(self, request, client_info):
        """Handle request to start a stream"""
        token = request.get("token")
        channel_name = request.get("channel")
        streamer_ip = request.get("streamer_ip")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if visitor (who can't stream)
        if username.startswith("visitor:"):
            return {"success": False, "type": MSG_ERROR, "message": "Visitors cannot start streams"}
        
        # Check if channel exists
        channel = db.get_channel(channel_name)
        if not channel:
            return {"success": False, "type": MSG_ERROR, "message": f"Channel {channel_name} not found"}
        
        # Check if this user owns the channel
        if channel["owner"] != username:
            return {"success": False, "type": MSG_ERROR, "message": "Only channel owner can start streams"}
        
        # Check if stream already exists
        if channel_name in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "Stream already active in this channel"}
        
        # Start new stream
        self.active_streams[channel_name] = {
            "streamer": username,
            "streamer_ip": streamer_ip,  # Store streamer's IP
            "viewers": set(),
            "start_time": datetime.now().isoformat()
        }
        
        system_logger.log_channel_event(channel_name, "stream_started", username)
        
        # Get online users
        online_users = db.get_online_users()
        print(f"Online users: {list(online_users.keys())}")  # Debug print
        
        # Add notifications for channel members who are online (except streamer)
        if channel:
            for member in channel["members"]:
                if member != username and member in online_users:
                    print(f"Adding stream notification for online channel member: {member}")  # Debug print
                    self._add_notification(
                        member,
                        "stream_start",
                        f"{username} started streaming in {channel_name}",
                        channel_name
                    )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Stream started successfully",
            "stream_info": {
                "streamer": username,
                "streamer_ip": streamer_ip,
                "start_time": self.active_streams[channel_name]["start_time"]
            }
        }
    
    def _handle_stream_end(self, request, client_info):
        """Handle request to end a stream"""
        token = request.get("token")
        channel_name = request.get("channel")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if stream exists
        if channel_name not in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "No active stream in this channel"}
        
        # Check if this user is the streamer
        if self.active_streams[channel_name]["streamer"] != username:
            return {"success": False, "type": MSG_ERROR, "message": "Only the streamer can end the stream"}
        
        # End stream
        stream_info = self.active_streams[channel_name]
        del self.active_streams[channel_name]
        
        system_logger.log_channel_event(channel_name, "stream_ended", username)
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Stream ended successfully",
            "stream_info": {
                "duration": (datetime.now() - datetime.fromisoformat(stream_info["start_time"])).total_seconds()
            }
        }
    
    def _handle_stream_join(self, request, client_info):
        """Handle request to join a stream"""
        token = request.get("token")
        channel_name = request.get("channel")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if stream exists
        if channel_name not in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "No active stream in this channel"}
        
        # Add viewer to stream
        self.active_streams[channel_name]["viewers"].add(username)
        
        system_logger.log_channel_event(channel_name, f"stream_joined by {username}", username)
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Joined stream successfully",
            "stream_info": {
                "streamer": self.active_streams[channel_name]["streamer"],
                "start_time": self.active_streams[channel_name]["start_time"]
            }
        }
    
    def _handle_stream_leave(self, request, client_info):
        """Handle request to leave a stream"""
        token = request.get("token")
        channel_name = request.get("channel")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if stream exists
        if channel_name not in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "No active stream in this channel"}
        
        # Remove viewer from stream
        if username in self.active_streams[channel_name]["viewers"]:
            self.active_streams[channel_name]["viewers"].remove(username)
        
        system_logger.log_channel_event(channel_name, f"stream_left by {username}", username)
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Left stream successfully"
        }
    
    def _handle_get_stream_info(self, request, client_info):
        """Handle request to get stream information"""
        token = request.get("token")
        channel_name = request.get("channel")
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if stream exists
        if channel_name not in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "No active stream in this channel"}
        
        # Return stream info
        stream_info = self.active_streams[channel_name]
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "stream_info": {
                "streamer": stream_info["streamer"],
                "streamer_ip": stream_info["streamer_ip"],  # Include IP in response
                "viewer_count": len(stream_info["viewers"]),
                "start_time": stream_info["start_time"]
            }
        }
    
    def _handle_stream_message(self, request, client_info):
        """Handle a stream chat message"""
        token = request.get("token")
        channel_name = request.get("channel")
        content = request.get("content")
        username = request.get("username")
        timestamp = request.get("timestamp")
        
        # Validate session
        valid, msg, _ = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Check if stream exists
        if channel_name not in self.active_streams:
            return {"success": False, "type": MSG_ERROR, "message": "No active stream in this channel"}
        
        # Create message object
        self.last_message_id += 1
        message = {
            "id": self.last_message_id,
            "username": username,
            "content": content,
            "timestamp": timestamp,
            "stream_id": self.active_streams[channel_name].get("stream_id", "")
        }
        
        # Store message
        if channel_name not in self.stream_messages:
            self.stream_messages[channel_name] = []
        self.stream_messages[channel_name].append(message)
        
        # Save messages to file
        self._save_stream_messages(channel_name)
        
        # Log the message
        system_logger.log_message(channel_name, username, self.last_message_id)
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Message sent successfully",
            "message_id": self.last_message_id
        }
    
    def _handle_get_stream_messages(self, request, client_info):
        """Handle request for stream chat messages"""
        token = request.get("token")
        channel_name = request.get("channel")
        since_id = request.get("since_id", 0)
        
        # Validate session
        valid, msg, _ = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
        
        # Get messages since the specified ID
        messages = []
        if channel_name in self.stream_messages:
            messages = [msg for msg in self.stream_messages[channel_name] if msg["id"] > since_id]
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "messages": messages
        }
    
    def _cleanup_routine(self):
        """Periodically cleanup expired sessions and inactive peers"""
        while self.running:
            # Cleanup expired sessions
            expired_sessions = auth.cleanup_expired_sessions()
            if expired_sessions > 0:
                print(f"Cleaned up {expired_sessions} expired sessions")
            
            # Sleep for 60 seconds before next cleanup
            time.sleep(60)

    async def stop_stream(self):
        """Stop the stream and save messages"""
        # ... existing stop_stream code ...
        
        # Save stream messages before clearing
        if self.channel in self.stream_messages:
            self._save_stream_messages(self.channel)

    def _load_stream_messages(self):
        """Load stream messages from JSON files"""
        try:
            for filename in os.listdir(self.stream_messages_dir):
                if filename.endswith('.json'):
                    channel_name = filename[:-5]  # Remove .json extension
                    file_path = os.path.join(self.stream_messages_dir, filename)
                    with open(file_path, 'r') as f:
                        messages = json.load(f)
                        self.stream_messages[channel_name] = messages
                        # Update last_message_id
                        if messages:
                            self.last_message_id = max(self.last_message_id,
                                                     max(msg.get('id', 0) for msg in messages))
        except Exception as e:
            print(f"Error loading stream messages: {e}")
    
    def _save_stream_messages(self, channel_name):
        """Save stream messages to JSON file"""
        try:
            file_path = os.path.join(self.stream_messages_dir, f"{channel_name}.json")
            with open(file_path, 'w') as f:
                json.dump(self.stream_messages.get(channel_name, []), f, indent=2)
        except Exception as e:
            print(f"Error saving stream messages: {e}")

    def _add_notification(self, username, notification_type, content, channel=None):
        """Add a notification for a user"""
        self.last_notification_id += 1
        notification = {
            "id": self.last_notification_id,
            "type": notification_type,
            "content": content,
            "channel": channel,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }
        
        if username not in self.notifications:
            self.notifications[username] = []
            
        self.notifications[username].append(notification)
        return notification

    def _handle_get_notifications(self, request, client_info):
        """Handle request to get user notifications"""
        token = request.get("token")
        since_id = request.get("since_id", 0)
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
            
        # Get unread notifications for user
        notifications = []
        if username in self.notifications:
            notifications = [n for n in self.notifications[username] 
                           if n["id"] > since_id and not n["read"]]
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "notifications": notifications
        }

    def _handle_mark_notifications_read(self, request, client_info):
        """Handle request to mark notifications as read"""
        token = request.get("token")
        notification_ids = request.get("notification_ids", [])
        
        # Validate session
        valid, msg, username = auth.validate_session(token)
        if not valid:
            return {"success": False, "type": MSG_ERROR, "message": msg}
            
        # Mark notifications as read
        if username in self.notifications:
            for notification in self.notifications[username]:
                if notification["id"] in notification_ids:
                    notification["read"] = True
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Notifications marked as read"
        }

def get_local_ip():
    """Get the local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                prog='Central Server',
                description='Centralized tracker for chat application',
                epilog='This server manages peer registration and channel coordination')
    
    parser.add_argument('--host', default=get_local_ip())
    parser.add_argument('--port', type=int, default=8000)
    
    args = parser.parse_args()
    
    server = CentralServer(args.host, args.port)
    server.start()