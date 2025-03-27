import socket
import threading
import json
import time
from datetime import datetime
import os
import queue
from logger import system_logger

# Protocol constants
MSG_JOIN = "JOIN"
MSG_LEAVE = "LEAVE"
MSG_MESSAGE = "MESSAGE"
MSG_CHANNEL_INFO = "CHANNEL_INFO"
MSG_HISTORY = "HISTORY"
MSG_SYNC = "SYNC"
MSG_SUCCESS = "SUCCESS"
MSG_ERROR = "ERROR"

class Peer:
    def __init__(self, username, host, port, central_server_host, central_server_port):
        self.username = username
        self.host = host
        self.port = port
        self.central_server = (central_server_host, central_server_port)
        self.peer_id = None
        self.token = None
        self.is_visitor = False
        self.status = "online"  # Default status: online or invisible
        
        # Peer server socket
        self.server_socket = None
        self.running = False
        
        # Active connections (username -> socket)
        self.connections = {}
        
        # Channel data storage
        self.channels = {}
        self.hosting_channels = []  # Channels this peer is hosting (owned by this user)
        self.joined_channels = []   # Channels this peer has joined (owned by other users)
        
        # Local message storage (channel -> list of messages)
        self.local_messages = {}
        
        # Offline message cache for when host is unavailable
        self.offline_cache = {}  # channel -> list of messages
        
        # Message queue for messages that need to be synchronized
        self.sync_queue = queue.Queue()
        
        # Thread for handling heartbeats to central server
        self.heartbeat_thread = None
        
        # Thread for syncing data to central server
        self.sync_thread = None
        
        # Thread for checking channel host status
        self.channel_status_thread = None
        
        # Add offline mode tracking
        self.is_offline = False
        self.offline_content = {}  # channel -> list of created content while offline
    
    def start(self):
        """Start the peer server"""
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            
            print(f"Peer server is listening on {self.host}:{self.port}")
            system_logger.log_connection(self.host, self.port, "0.0.0.0", 0, "peer_server_started")
            
            self.running = True
            
            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_routine)
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()
            
            # Start sync thread if not a visitor
            if not self.is_visitor:
                self.sync_thread = threading.Thread(target=self._sync_routine)
                self.sync_thread.daemon = True
                self.sync_thread.start()
                
                # Start channel status thread
                self.channel_status_thread = threading.Thread(target=self._channel_status_routine)
                self.channel_status_thread.daemon = True
                self.channel_status_thread.start()
            
            # Main server loop
            server_thread = threading.Thread(target=self._server_loop)
            server_thread.daemon = True
            server_thread.start()
            
            return True
        except Exception as e:
            print(f"Failed to start peer server: {e}")
            return False
    
    def _server_loop(self):
        """Main loop for the peer server"""
        while self.running:
            try:
                # Accept connection from other peer
                client_socket, client_addr = self.server_socket.accept()
                
                # Start a new thread to handle this peer
                client_handler = threading.Thread(
                    target=self._handle_peer,
                    args=(client_socket, client_addr)
                )
                client_handler.daemon = True
                client_handler.start()
                
            except Exception as e:
                if self.running:  # Only print error if we're still supposed to be running
                    print(f"Error accepting connection: {e}")
    
    def stop(self):
        """Stop the peer server"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        
        # Close all connections
        for peer_socket in self.connections.values():
            peer_socket.close()
        
        # Wait for threads to finish
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=1)
        
        if self.sync_thread and self.sync_thread.is_alive():
            self.sync_thread.join(timeout=1)
            
        if self.channel_status_thread and self.channel_status_thread.is_alive():
            self.channel_status_thread.join(timeout=1)
        
        print("Peer server stopped")
    
    def _handle_peer(self, peer_socket, peer_addr):
        """Handle incoming peer connection"""
        try:
            # Receive initial message
            data = peer_socket.recv(4096).decode('utf-8')
            if not data:
                return
            
            # Parse the message
            request = json.loads(data)
            message_type = request.get("type")
            
            response = {"success": False, "message": "Unknown request type"}
            
            # Process the request based on its type
            if message_type == MSG_JOIN:
                response = self._handle_join(request, peer_socket, peer_addr)
            elif message_type == MSG_LEAVE:
                response = self._handle_leave(request, peer_socket, peer_addr)
            elif message_type == MSG_MESSAGE:
                response = self._handle_message(request, peer_socket, peer_addr)
            elif message_type == MSG_CHANNEL_INFO:
                response = self._handle_channel_info(request, peer_socket, peer_addr)
            elif message_type == MSG_HISTORY:
                response = self._handle_history(request, peer_socket, peer_addr)
            elif message_type == MSG_SYNC:
                response = self._handle_sync(request, peer_socket, peer_addr)
            
            # Send response
            peer_socket.sendall(json.dumps(response).encode('utf-8'))
            
            # Keep connection open for channel streaming if this is a join request
            if message_type == MSG_JOIN and response["success"]:
                channel_name = request.get("channel")
                username = request.get("username")
                
                # Store the connection
                self.connections[f"{username}:{channel_name}"] = peer_socket
                
                # Keep listening for messages from this peer
                while self.running:
                    try:
                        # Use a timeout to periodically check if we're still running
                        peer_socket.settimeout(1.0)
                        data = peer_socket.recv(4096).decode('utf-8')
                        
                        if not data:
                            break
                        
                        # Parse and handle the message
                        request = json.loads(data)
                        message_type = request.get("type")
                        
                        if message_type == MSG_MESSAGE:
                            self._handle_message(request, peer_socket, peer_addr)
                        elif message_type == MSG_LEAVE:
                            self._handle_leave(request, peer_socket, peer_addr)
                            break
                        
                    except socket.timeout:
                        # This is normal, just check if we should keep running
                        continue
                    except Exception as e:
                        print(f"Error reading from peer: {e}")
                        break
                
                # Remove from connections when done
                self.connections.pop(f"{username}:{channel_name}", None)
            
        except Exception as e:
            print(f"Error handling peer {peer_addr}: {e}")
            
            # Send error response
            error_response = {
                "success": False,
                "type": MSG_ERROR,
                "message": str(e)
            }
            try:
                peer_socket.sendall(json.dumps(error_response).encode('utf-8'))
            except:
                pass
        
        finally:
            # Don't close the socket here if it's stored in connections
            pass
    
    def _handle_join(self, request, peer_socket, peer_addr):
        """Handle request to join a channel"""
        channel_name = request.get("channel")
        username = request.get("username")
        
        # Check if we're hosting this channel
        if channel_name not in self.hosting_channels:
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": f"Not hosting channel {channel_name}"
            }
        
        # Log the join
        ip, port = peer_addr
        system_logger.log_connection(
            ip, port, self.host, self.port, 
            f"peer_joined_channel:{username}:{channel_name}"
        )
        
        # Get channel messages
        messages = self.local_messages.get(channel_name, [])
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Joined channel {channel_name}",
            "host": self.username,
            "last_message_id": len(messages)
        }
    
    def _handle_leave(self, request, peer_socket, peer_addr):
        """Handle request to leave a channel"""
        channel_name = request.get("channel")
        username = request.get("username")
        
        # Log the leave
        ip, port = peer_addr
        system_logger.log_connection(
            ip, port, self.host, self.port, 
            f"peer_left_channel:{username}:{channel_name}"
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Left channel {channel_name}"
        }
    
    def _handle_message(self, request, peer_socket, peer_addr):
        """Handle incoming message for a channel"""
        channel_name = request.get("channel")
        username = request.get("username")
        content = request.get("content")
        
        # Make sure we're hosting this channel
        if channel_name not in self.hosting_channels:
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": f"Not hosting channel {channel_name}"
            }

        # Visitors should not be able to send messages
        if username.startswith("visitor:"):
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": "Visitors cannot send messages"
            }
        
        # Create message object
        timestamp = datetime.now().isoformat()
        message = {
            "id": len(self.local_messages.get(channel_name, [])) + 1,
            "username": username,
            "content": content,
            "timestamp": timestamp
        }
        
        # Store message locally
        if channel_name not in self.local_messages:
            self.local_messages[channel_name] = []
        self.local_messages[channel_name].append(message)
        
        # Add to sync queue for backup to central server
        self.sync_queue.put((channel_name, message))
        
        # Send to connected peers individually
        broadcast = {
            "type": MSG_MESSAGE,
            "channel": channel_name,
            "message": message
        }
        
        for conn_id, conn_socket in list(self.connections.items()):
            if conn_id.endswith(f":{channel_name}") and conn_socket != peer_socket:
                try:
                    # Extract username from connection ID
                    recipient_username = conn_id.split(":")[0]
                    
                    # Check if recipient is offline using server request
                    request = {
                        "type": "GET_USER_STATUS",
                        "token": self.token,
                        "username": recipient_username
                    }
                    
                    response = self._send_to_central_server(request)
                    if response.get("success") and response.get("status") == "offline":
                        print(f"Skipping offline recipient: {recipient_username}")
                        continue
                        
                    conn_socket.sendall(json.dumps(broadcast).encode('utf-8'))
                except Exception as e:
                    print(f"Error sending to {conn_id}: {e}")
                    # Remove failed connection
                    self.connections.pop(conn_id, None)
        
        # Log the message
        ip, port = peer_addr
        system_logger.log_data_transfer(
            ip, port, self.host, self.port, 
            len(content), f"message_received:{channel_name}"
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": "Message received",
            "message_id": message["id"]
        }
    
    def _handle_channel_info(self, request, peer_socket, peer_addr):
        """Handle request for channel information"""
        channel_name = request.get("channel")
        
        # Check if we're hosting this channel
        if channel_name not in self.hosting_channels:
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": f"Not hosting channel {channel_name}"
            }
        
        # Get channel info
        message_count = len(self.local_messages.get(channel_name, []))
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "channel": channel_name,
            "message_count": message_count,
            "host": self.username
        }
    
    def _handle_history(self, request, peer_socket, peer_addr):
        """Handle request for channel message history"""
        channel_name = request.get("channel")
        since_id = int(request.get("since_id", 0))
        limit = int(request.get("limit", 50))
        
        # Check if we're hosting this channel
        if channel_name not in self.hosting_channels:
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": f"Not hosting channel {channel_name}"
            }
        
        # Get messages
        all_messages = self.local_messages.get(channel_name, [])
        filtered_messages = [msg for msg in all_messages if msg["id"] > since_id]
        
        # Apply limit
        messages = filtered_messages[-limit:] if limit > 0 else filtered_messages
        
        # Log the data transfer
        ip, port = peer_addr
        system_logger.log_data_transfer(
            self.host, self.port, ip, port, 
            len(json.dumps(messages).encode('utf-8')), 
            f"history_sent:{channel_name}"
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "channel": channel_name,
            "messages": messages,
            "total_count": len(all_messages)
        }
    
    def _handle_sync(self, request, peer_socket, peer_addr):
        """Handle request to sync channel data"""
        channel_name = request.get("channel")
        messages = request.get("messages", [])
        
        # Only the channel owner should be sending sync requests
        if channel_name not in self.channels or self.channels[channel_name].get("owner") != request.get("username"):
            return {
                "success": False,
                "type": MSG_ERROR,
                "message": "Only channel owner can sync data"
            }
        
        # Update local messages
        if channel_name not in self.local_messages:
            self.local_messages[channel_name] = []
        
        # Add new messages
        self.local_messages[channel_name].extend(messages)
        
        # Log the sync
        ip, port = peer_addr
        system_logger.log_data_transfer(
            ip, port, self.host, self.port, 
            len(json.dumps(messages).encode('utf-8')), 
            f"sync_received:{channel_name}"
        )
        
        return {
            "success": True,
            "type": MSG_SUCCESS,
            "message": f"Synced {len(messages)} messages for channel {channel_name}"
        }
    
    def _heartbeat_routine(self):
        """Periodically send heartbeat to central server"""
        while self.running:
            if self.peer_id and self.token:
                try:
                    # Create heartbeat request
                    request = {
                        "type": "HEARTBEAT",
                        "peer_id": self.peer_id,
                        "token": self.token,
                        "status": self.status,
                        "hosting_channels": self.hosting_channels
                    }
                    
                    # Send to central server
                    response = self._send_to_central_server(request)
                    
                    if not response.get("success"):
                        print(f"Heartbeat failed: {response.get('message')}")
                    
                except Exception as e:
                    print(f"Error sending heartbeat: {e}")
            
            # Sleep for 30 seconds
            time.sleep(30)
    
    def _sync_routine(self):
        """Periodically sync messages to central server"""
        while self.running:
            if self.peer_id and self.token and not self.is_visitor:
                try:
                    # Process messages in the sync queue
                    messages_by_channel = {}
                    
                    # Collect up to 20 messages to sync
                    for _ in range(20):
                        try:
                            channel_name, message = self.sync_queue.get_nowait()
                            
                            if channel_name not in messages_by_channel:
                                messages_by_channel[channel_name] = []
                            
                            messages_by_channel[channel_name].append(message)
                            self.sync_queue.task_done()
                            
                        except queue.Empty:
                            break
                    
                    # Sync each channel's messages to central server
                    for channel_name, messages in messages_by_channel.items():
                        # Create sync request
                        request = {
                            "type": "SYNC_DATA",
                            "token": self.token,
                            "channel": channel_name,
                            "messages": messages
                        }
                        
                        # Send to central server
                        response = self._send_to_central_server(request)
                        
                        if not response.get("success"):
                            print(f"Sync failed for {channel_name}: {response.get('message')}")
                            # Put messages back in queue for retry
                            for msg in messages:
                                self.sync_queue.put((channel_name, msg))
                        else:
                            print(f"Synced {len(messages)} messages for channel {channel_name}")
                            system_logger.log_channel_event(
                                channel_name, 
                                f"data_synced with {len(messages)} messages", 
                                self.username
                            )
                    
                    # Check for offline cached messages that need to be sent
                    self._process_offline_cache()
                    
                except Exception as e:
                    print(f"Error in sync routine: {e}")
            
            # Sleep for 60 seconds
            time.sleep(60)
    
    def _channel_status_routine(self):
        """Periodically check status of channels and hosts"""
        while self.running:
            if self.peer_id and self.token and not self.is_visitor:
                try:
                    # Check status of hosted channels first
                    for channel_name in self.hosting_channels:
                        # If we're hosting, make sure we sync with server
                        if channel_name in self.local_messages:
                            self._sync_with_central_server(channel_name)
                    
                    # Check joined channels
                    for channel_name in list(self.joined_channels):
                        host = self.get_channel_host(channel_name)
                        conn_id = f"{self.username}:{channel_name}"
                        
                        if not host:
                            # Host is offline
                            if conn_id in self.connections:
                                print(f"Host for channel {channel_name} is offline")
                                # Close and remove connection
                                peer_socket = self.connections.pop(conn_id)
                                peer_socket.close()
                                
                                # Sync with central server
                                self._sync_from_central_server(channel_name)
                        else:
                            # Host is online but we don't have connection
                            if conn_id not in self.connections:
                                print(f"Reconnecting to {channel_name} - host is online")
                                if self.join_channel(channel_name):
                                    # Process any cached messages
                                    self._send_cached_messages(channel_name)
                                    # Get latest messages from host
                                    self._sync_from_host(channel_name, host)
                
                except Exception as e:
                    print(f"Error in channel status routine: {e}")
            
            # Check every 30 seconds instead of 120
            time.sleep(30)
    
    def _process_offline_cache(self):
        """Process messages that were cached while hosts were offline"""
        # For each channel with cached messages
        for channel_name in list(self.offline_cache.keys()):
            if not self.offline_cache[channel_name]:
                continue
                
            # Try to send cached messages
            self._send_cached_messages(channel_name)
    
    def _send_cached_messages(self, channel_name):
        """Attempt to send cached messages for a channel"""
        if channel_name not in self.offline_cache or not self.offline_cache[channel_name]:
            return
            
        # Check if we have a connection to the host
        conn_id = f"{self.username}:{channel_name}"
        if conn_id in self.connections:
            # We have a direct connection to the host, send P2P
            peer_socket = self.connections[conn_id]
            
            # Send each cached message
            messages_to_remove = []
            for message_data in self.offline_cache[channel_name]:
                try:
                    message = {
                        "type": MSG_MESSAGE,
                        "channel": channel_name,
                        "username": self.username,
                        "content": message_data["content"]
                    }
                    
                    peer_socket.sendall(json.dumps(message).encode('utf-8'))
                    
                    # Wait for response
                    response_data = peer_socket.recv(4096).decode('utf-8')
                    response = json.loads(response_data)
                    
                    if response.get("success"):
                        messages_to_remove.append(message_data)
                    
                except Exception as e:
                    print(f"Error sending cached message to host: {e}")
                    break
            
            # Remove sent messages from cache
            for message in messages_to_remove:
                self.offline_cache[channel_name].remove(message)
                
            print(f"Sent {len(messages_to_remove)} cached messages to {channel_name} host")
            
        else:
            # No direct connection, try to send via central server
            host = self.get_channel_host(channel_name)
            
            if not host:
                # No host available, send to central server
                messages_to_remove = []
                for message_data in self.offline_cache[channel_name]:
                    request = {
                        "type": "SEND_MESSAGE",
                        "token": self.token,
                        "channel": channel_name,
                        "content": message_data["content"]
                    }
                    
                    response = self._send_to_central_server(request)
                    
                    if response.get("success"):
                        messages_to_remove.append(message_data)
                    else:
                        print(f"Failed to send cached message via server: {response.get('message')}")
                
                # Remove sent messages from cache
                for message in messages_to_remove:
                    self.offline_cache[channel_name].remove(message)
                    
                print(f"Sent {len(messages_to_remove)} cached messages to central server for {channel_name}")
            else:
                # Host exists but we don't have a connection, try to establish one
                if channel_name not in self.joined_channels:
                    self.joined_channels.append(channel_name)
                    
                if self.join_channel(channel_name):
                    # Now we have a connection, call this method again
                    self._send_cached_messages(channel_name)
    
    def _send_to_central_server(self, request):
        """Send a request to the central server and get the response"""
        try:
            # Create socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Connect to server
            client_socket.connect(self.central_server)
            
            # Send request
            client_socket.sendall(json.dumps(request).encode('utf-8'))
            
            # Receive response
            response_data = client_socket.recv(4096).decode('utf-8')
            
            # Parse response
            response = json.loads(response_data)
            
            # Close socket
            client_socket.close()
            
            return response
            
        except Exception as e:
            print(f"Error sending to central server: {e}")
            return {"success": False, "message": str(e)}
    
    def register_with_central_server(self, token):
        """Register this peer with the central server"""
        self.token = token
        
        # Create registration request
        request = {
            "type": "REGISTER",
            "token": token,
            "port": self.port
        }
        
        # Send to central server
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.peer_id = response.get("peer_id")
            print(f"Registered with central server as {self.peer_id}")
            return True
        else:
            print(f"Failed to register with central server: {response.get('message')}")
            return False
    
    def host_channel(self, channel_name):
        """Start hosting a channel"""
        if self.is_visitor:
            print("Visitors cannot host channels")
            return False
        
        # Request to host channel
        request = {
            "type": "CHANNEL_HOST",
            "token": self.token,
            "channel": channel_name,
            "port": self.port,
            "action": "host"
        }
        
        # Send to central server
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.hosting_channels.append(channel_name)
            print(f"Now hosting channel {channel_name}")
            system_logger.log_channel_event(channel_name, "hosting", self.username)
            
            # Initialize local message storage if needed
            if channel_name not in self.local_messages:
                self.local_messages[channel_name] = []
                
                # Sync with central server to get existing messages
                self._sync_from_central_server(channel_name)
                
            return True
        else:
            print(f"Failed to host channel: {response.get('message')}")
            return False
    
    def _sync_from_central_server(self, channel_name):
        """Sync channel data from central server"""
        request = {
            "type": "GET_HISTORY",
            "token": self.token,
            "channel": channel_name,
            "since_id": 0,
            "limit": 0  # No limit, get all messages
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            messages = response.get("messages", [])
            
            if channel_name not in self.local_messages:
                self.local_messages[channel_name] = []
                
            # Add messages that don't already exist
            for message in messages:
                # Check if message already exists
                exists = False
                for existing_msg in self.local_messages[channel_name]:
                    if existing_msg.get("id") == message.get("id"):
                        exists = True
                        break
                
                if not exists:
                    self.local_messages[channel_name].append(message)
            
            print(f"Synced {len(messages)} messages from central server for channel {channel_name}")
            return True
        else:
            print(f"Failed to sync from central server: {response.get('message')}")
            return False
    
    def release_channel(self, channel_name):
        """Stop hosting a channel"""
        if channel_name not in self.hosting_channels:
            return False
        
        # Request to release channel
        request = {
            "type": "CHANNEL_HOST",
            "token": self.token,
            "channel": channel_name,
            "port": self.port,
            "action": "release"
        }
        
        # Send to central server
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.hosting_channels.remove(channel_name)
            print(f"Released channel {channel_name}")
            system_logger.log_channel_event(channel_name, "released", self.username)
            return True
        else:
            print(f"Failed to release channel: {response.get('message')}")
            return False
    
    def get_channel_host(self, channel_name):
        """Find the peer hosting a channel"""
        request = {
            "type": "GET_PEERS",
            "token": self.token,
            "channel": channel_name
        }
        
        # Send to central server
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            return response.get("host")
        else:
            print(f"Failed to find channel host: {response.get('message')}")
            return None
    
    def join_channel(self, channel_name):
        """Join a channel hosted by another peer"""
        # Check if already joined
        if channel_name in self.joined_channels:
            # If we're already joined but don't have a connection, try to reconnect
            conn_id = f"{self.username}:{channel_name}"
            if conn_id not in self.connections:
                # Find who is hosting the channel
                host = self.get_channel_host(channel_name)
                if not host:
                    print(f"No host found for channel {channel_name}")
                    return False
                    
                # Try to connect to host
                try:
                    self._connect_to_channel_host(channel_name, host)
                    return True
                except Exception as e:
                    print(f"Failed to reconnect to channel {channel_name}: {e}")
                    return False
            return True
        
        # Find who is hosting the channel
        host = self.get_channel_host(channel_name)
        
        if not host:
            print(f"No host found for channel {channel_name}")
            # Join channel via central server instead
            return self._join_channel_via_server(channel_name)
        
        # Try to join via P2P first
        try:
            # Connect to host
            self._connect_to_channel_host(channel_name, host)
            
            # Add to joined channels
            if channel_name not in self.joined_channels:
                self.joined_channels.append(channel_name)
                
            print(f"Joined channel {channel_name} via P2P")
            return True
            
        except Exception as e:
            print(f"Error joining channel via P2P: {e}")
            # Fall back to joining via central server
            return self._join_channel_via_server(channel_name)
    
    def _connect_to_channel_host(self, channel_name, host):
        """Connect to a channel host"""
        host_ip = host["ip"]
        host_port = host["port"]
        
        # Create socket
        peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Connect to host
        peer_socket.connect((host_ip, host_port))
        
        # Send join request
        join_request = {
            "type": MSG_JOIN,
            "channel": channel_name,
            "username": self.username
        }
        
        peer_socket.sendall(json.dumps(join_request).encode('utf-8'))
        
        # Receive response
        response_data = peer_socket.recv(4096).decode('utf-8')
        response = json.loads(response_data)
        
        if response.get("success"):
            # Store the channel and connection
            self.connections[f"{self.username}:{channel_name}"] = peer_socket
            
            # Start a thread to listen for messages from this channel
            channel_listener = threading.Thread(
                target=self._channel_listener,
                args=(channel_name, peer_socket)
            )
            channel_listener.daemon = True
            channel_listener.start()
            
            return True
        else:
            raise Exception(f"Host rejected join request: {response.get('message')}")
    
    def _join_channel_via_server(self, channel_name):
        """Join a channel through the central server"""
        request = {
            "type": "JOIN_CHANNEL",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            # Add to joined channels
            if channel_name not in self.joined_channels:
                self.joined_channels.append(channel_name)
                
            print(f"Joined channel {channel_name} via central server")
            
            # Initialize local cache for this channel
            if channel_name not in self.local_messages:
                self.local_messages[channel_name] = []
                
            # Get existing messages
            self._sync_from_central_server(channel_name)
            
            return True
        else:
            print(f"Failed to join channel via server: {response.get('message')}")
            return False
    
    def _channel_listener(self, channel_name, peer_socket):
        """Listen for messages from a channel"""
        try:
            while self.running and channel_name in self.joined_channels:
                # Use a timeout to periodically check if we're still running
                peer_socket.settimeout(1.0)
                
                try:
                    # Check our status first - if we're offline, don't process any messages
                    if self.status == "offline":
                        time.sleep(1)  # Sleep to avoid busy waiting
                        continue
                        
                    data = peer_socket.recv(4096).decode('utf-8')
                    
                    if not data:
                        break
                        
                    # Parse message
                    message = json.loads(data)
                    
                    # Handle message based on type
                    if message.get("type") == MSG_MESSAGE:
                        # Process incoming message
                        self._process_channel_message(channel_name, message.get("message"))
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error reading from channel {channel_name}: {e}")
                    break
                    
            if channel_name in self.joined_channels:
                self.leave_channel(channel_name)
                
        except Exception as e:
            print(f"Channel listener error for {channel_name}: {e}")
            
            if channel_name in self.joined_channels:
                self.joined_channels.remove(channel_name)
            
            self.connections.pop(f"{self.username}:{channel_name}", None)
            
            if peer_socket:
                peer_socket.close()
    
    def _process_channel_message(self, channel_name, message):
        """Process a message received from a channel"""
        # This is where the application would handle a received message
        print(f"[{channel_name}] {message['username']}: {message['content']}")
        
        # Store message locally if not already present
        if channel_name not in self.local_messages:
            self.local_messages[channel_name] = []
        
        # Check if message already exists by ID
        exists = False
        for existing_msg in self.local_messages[channel_name]:
            if existing_msg.get("id") == message.get("id"):
                exists = True
                break
        
        if not exists:
            self.local_messages[channel_name].append(message)
    
    def leave_channel(self, channel_name):
        """Leave a channel"""
        if channel_name not in self.joined_channels:
            return True
        
        # Get the connection
        conn_id = f"{self.username}:{channel_name}"
        peer_socket = self.connections.get(conn_id)
        
        if peer_socket:
            try:
                # Send leave request
                leave_request = {
                    "type": MSG_LEAVE,
                    "channel": channel_name,
                    "username": self.username
                }
                
                peer_socket.sendall(json.dumps(leave_request).encode('utf-8'))
                
                # Close the socket
                peer_socket.close()
                
            except Exception as e:
                print(f"Error leaving channel {channel_name}: {e}")
            
            # Remove from connections
            self.connections.pop(conn_id, None)
        
        # Remove from joined channels
        self.joined_channels.remove(channel_name)
        
        print(f"Left channel {channel_name}")
        return True
    
    def send_message(self, channel_name, content):
        """Send a message to a channel"""
        # Check if user is a visitor (view-only)
        if self.is_visitor:
            print(f"Visitors cannot send messages - view-only mode")
            return False
            
        if channel_name not in self.joined_channels and channel_name not in self.hosting_channels:
            print(f"Not connected to channel {channel_name}")
            return False
        
        # Create message object for tracking
        timestamp = datetime.now().isoformat()
        message = {
            "id": len(self.local_messages.get(channel_name, [])) + 1,
            "username": self.username,
            "content": content,
            "timestamp": timestamp
        }
        
        if channel_name in self.hosting_channels:
            # We're hosting this channel, send to each connected peer individually
            broadcast_message = {
                "type": MSG_MESSAGE,
                "channel": channel_name,
                "message": message
            }
            
            # Store message locally first
            if channel_name not in self.local_messages:
                self.local_messages[channel_name] = []
            self.local_messages[channel_name].append(message)
            
            # Send to each connection individually
            for conn_id, conn_socket in list(self.connections.items()):
                if conn_id.endswith(f":{channel_name}"):
                    try:
                        # Extract username from connection ID
                        recipient_username = conn_id.split(":")[0]
                        
                        # Check if recipient is offline
                        request = {
                            "type": "GET_USER_STATUS",
                            "token": self.token,
                            "username": recipient_username
                        }
                        
                        response = self._send_to_central_server(request)
                        if response.get("success") and response.get("status") == "offline":
                            print(f"Skipping offline recipient: {recipient_username}")
                            continue
                            
                        conn_socket.sendall(json.dumps(broadcast_message).encode('utf-8'))
                    except Exception as e:
                        print(f"Error sending to {conn_id}: {e}")
                        # Remove failed connection
                        self.connections.pop(conn_id, None)
            
            # Also sync to central server as backup
            self.sync_queue.put((channel_name, message))
            return True
            
        else:
            # We're joined to this channel, try to send to the host
            conn_id = f"{self.username}:{channel_name}"
            peer_socket = self.connections.get(conn_id)
            
            if peer_socket:
                # We have a direct connection to the host, send via P2P
                try:
                    peer_socket.sendall(json.dumps(message).encode('utf-8'))
                    return True
                except Exception as e:
                    print(f"Error sending message via P2P: {e}")
                    # Fall back to caching for later delivery
                    self._cache_message_for_later(channel_name, message)
                    return False
            else:
                # No direct connection to host
                host = self.get_channel_host(channel_name)
                
                if host:
                    # Host exists but we don't have a connection, try to establish one
                    try:
                        if self.join_channel(channel_name):
                            # Now we have a connection, try to send again
                            return self.send_message(channel_name, content)
                        else:
                            # Failed to join, cache for later
                            self._cache_message_for_later(channel_name, message)
                            return False
                    except Exception as e:
                        print(f"Error reconnecting to channel: {e}")
                        # Cache for later
                        self._cache_message_for_later(channel_name, message)
                        return False
                else:
                    # No host available, send through central server
                    request = {
                        "type": "SEND_MESSAGE",
                        "token": self.token,
                        "channel": channel_name,
                        "content": content
                    }
                    
                    response = self._send_to_central_server(request)
                    
                    if response.get("success"):
                        print(f"Message sent via central server")
                        return True
                    else:
                        print(f"Failed to send message via server: {response.get('message')}")
                        # Cache for later delivery
                        self._cache_message_for_later(channel_name, message)
                        return False
    
    def _cache_message_for_later(self, channel_name, message):
        """Cache a message for later delivery"""
        if channel_name not in self.offline_cache:
            self.offline_cache[channel_name] = []
            
        self.offline_cache[channel_name].append(message)
        print(f"Message cached for later delivery to {channel_name}")
    
    def get_channel_history(self, channel_name, since_id=0, limit=50):
        """Get message history for a channel"""
        try:
            # If we're hosting, get from local storage
            if channel_name in self.hosting_channels:
                all_messages = self.local_messages.get(channel_name, [])
                filtered_messages = [msg for msg in all_messages if msg["id"] > since_id]
                return filtered_messages[-limit:] if limit > 0 else filtered_messages

            # Fall back to central server
            print(f"Getting history from central server for {channel_name}")
            request = {
                "type": "GET_HISTORY",
                "token": self.token,
                "channel": channel_name,
                "since_id": since_id,
                "limit": limit
            }

            response = self._send_to_central_server(request)
            if response.get("success"):
                messages = response.get("messages", [])
                print(f"Received {len(messages)} messages from central server")
                
                # Update local cache
                if messages:
                    if channel_name not in self.local_messages:
                        self.local_messages[channel_name] = []
                    for msg in messages:
                        # Only add messages we don't already have
                        if not any(existing["id"] == msg["id"] for existing in self.local_messages[channel_name]):
                            self.local_messages[channel_name].append(msg)
                
                return messages
            else:
                print(f"Failed to get history from central server: {response.get('message')}")
                return []
                
        except Exception as e:
            print(f"Error in get_channel_history: {e}")
            return []
    
    def _update_local_messages(self, channel_name, messages):
        """Update local message cache with new messages"""
        if not messages:
            return
            
        if channel_name not in self.local_messages:
            self.local_messages[channel_name] = []
        
        # Add messages that don't already exist
        for message in messages:
            exists = False
            for existing_msg in self.local_messages[channel_name]:
                if existing_msg.get("id") == message.get("id"):
                    exists = True
                    break
            
            if not exists:
                self.local_messages[channel_name].append(message)
    
    def set_status(self, status):
        """Set user's status (online, offline, or invisible)"""
        if self.is_visitor:
            print("Visitors cannot change status")
            return False
        
        if status not in ["online", "offline", "invisible"]:
            print("Invalid status. Must be 'online', 'offline', or 'invisible'")
            return False
        
        # Update status on server
        request = {
            "type": "STATUS",
            "token": self.token,
            "status": status
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.status = status
            print(f"Status changed to {status}")
            return True
        else:
            print(f"Failed to change status: {response.get('message')}")
            return False
    
    def get_online_users(self):
        """Get list of online users"""
        request = {
            "type": "GET_ONLINE_USERS",
            "token": self.token
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            return response.get("users", [])
        else:
            print(f"Failed to get online users: {response.get('message')}")
            return []
    
    def set_is_visitor(self, is_visitor):
        """Set whether this peer is a visitor"""
        self.is_visitor = is_visitor
        
        # If becoming a visitor, stop hosting all channels
        if is_visitor and self.hosting_channels:
            for channel in list(self.hosting_channels):
                self.release_channel(channel)
    
    def _sync_from_host(self, channel_name, host):
        """Sync messages directly from a channel host"""
        if not host:
            return False
            
        # Create history request to get all messages
        history_request = {
            "type": MSG_HISTORY,
            "channel": channel_name,
            "username": self.username,
            "since_id": 0,
            "limit": 0  # No limit = get all messages
        }
        
        # Get connection to host
        conn_id = f"{self.username}:{channel_name}"
        peer_socket = self.connections.get(conn_id)
        
        if not peer_socket:
            return False
            
        try:
            # Send request
            peer_socket.sendall(json.dumps(history_request).encode('utf-8'))
            
            # Get response
            response_data = peer_socket.recv(4096).decode('utf-8')
            response = json.loads(response_data)
            
            if response.get("success"):
                messages = response.get("messages", [])
                self._update_local_messages(channel_name, messages)
                print(f"Synced {len(messages)} messages from host for {channel_name}")
                return True
            else:
                print(f"Failed to sync from host: {response.get('message')}")
                return False
                
        except Exception as e:
            print(f"Error syncing from host: {e}")
            return False
    
    def _sync_with_central_server(self, channel_name):
        """Sync local messages to central server"""
        if channel_name not in self.local_messages:
            return True
            
        # Get last synced message ID from server
        history_request = {
            "type": "GET_HISTORY",
            "token": self.token,
            "channel": channel_name,
            "since_id": 0,
            "limit": 1
        }
        
        response = self._send_to_central_server(history_request)
        last_server_id = 0
        
        if response.get("success"):
            messages = response.get("messages", [])
            if messages:
                last_server_id = messages[-1].get("id", 0)
        
        # Find messages that need to be synced
        messages_to_sync = []
        for message in self.local_messages[channel_name]:
            if message.get("id", 0) > last_server_id:
                messages_to_sync.append(message)
        
        if not messages_to_sync:
            return True
            
        # Create sync request
        sync_request = {
            "type": "SYNC_DATA",
            "token": self.token,
            "channel": channel_name,
            "messages": messages_to_sync
        }
        
        # Send to central server
        response = self._send_to_central_server(sync_request)
        
        if response.get("success"):
            print(f"Synced {len(messages)} messages to central server for {channel_name}")
            system_logger.log_channel_event(
                channel_name, 
                f"data_synced with {len(messages)} messages", 
                self.username
            )
            return True
        else:
            print(f"Failed to sync with central server: {response.get('message')}")
            return False
    
    def set_offline_mode(self, is_offline):
        """Set peer's offline mode explicitly"""
        self.is_offline = is_offline
        if not is_offline and self.offline_content:
            # When coming back online, try to sync offline content
            self._sync_offline_content()
    
    def _sync_offline_content(self):
        """Sync content created while offline"""
        if not self.offline_content:
            return
            
        print("Syncing offline content...")
        for channel_name, messages in self.offline_content.items():
            if not messages:
                continue
                
            if channel_name in self.hosting_channels:
                # We're the host, sync directly to server
                self._sync_with_central_server(channel_name)
            else:
                # We're a joined user, try to sync with host first
                host = self.get_channel_host(channel_name)
                if host:
                    # Try P2P sync first
                    self._sync_from_host(channel_name, host)
                
                # Sync with central server as backup
                for message in messages:
                    request = {
                        "type": "SEND_MESSAGE",
                        "token": self.token,
                        "channel": channel_name,
                        "content": message["content"]
                    }
                    response = self._send_to_central_server(request)
                    if response.get("success"):
                        print(f"Synced offline message to server for {channel_name}")
                        
            # Clear synced messages
            self.offline_content[channel_name] = []
