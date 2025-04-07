import argparse
import getpass
import socket
import threading
import json
import time
import os
import readline
import signal
import sys

from peer import Peer
from authentication import auth
from database import db
from logger import system_logger


class ChatClient:
    def __init__(self, central_server_host, central_server_port):
        self.central_server_host = central_server_host
        self.central_server_port = central_server_port
        self.username = None
        self.token = None
        self.is_visitor = False
        self.peer = None
        self.running = False
        self.current_channel = None
        self.command_history = []
        self.message_cache = {}  # Cache for messages by channel
        
        # Comment out stream-related state
        # self.current_stream = None
        # self.stream_viewers = set()
        
        # Setup readline for command history
        readline.set_history_length(100)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_interrupt)
        
    def _handle_interrupt(self, sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\nExiting chat application...")
        self.logout()
        sys.exit(0)
        
    def _send_to_central_server(self, request):
        """Send a request to the central server and get the response"""
        try:
            # Create socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)  # Add timeout
            
            try:
                # Connect to server
                client_socket.connect((self.central_server_host, self.central_server_port))
                
                # Send request
                client_socket.sendall(json.dumps(request).encode('utf-8'))
                
                # Receive response
                response_data = client_socket.recv(65536).decode('utf-8')  # Increased buffer size
                
                try:
                    response = json.loads(response_data)
                    return response
                except json.JSONDecodeError as e:
                    print(f"Error sending to central server: {e}")
                    return {"success": False, "message": str(e)}
                
            finally:
                client_socket.close()
                
        except Exception as e:
            print(f"Error sending to central server: {e}")
            return {"success": False, "message": str(e)}
    
    def start(self):
        """Start the chat client"""
        self.running = True
        self._show_welcome()
        
        while self.running:
            if not self.token:
                self._show_login_menu()
            else:
                self._show_main_menu()
                
    def _show_welcome(self):
        """Show welcome message"""
        print("\n" + "=" * 50)
        print("  DISCORD-LIKE CHAT APPLICATION  ".center(50))
        print("=" * 50)
        print("\nWelcome to the Chat Application!")
        print("This application allows you to chat with others using")
        print("a hybrid client-server and peer-to-peer architecture.")
    
    def _show_login_menu(self):
        """Show login menu"""
        print("\n--- Login Options ---")
        print("1. Login as registered user")
        print("2. Login as visitor")
        print("3. Register a new account")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == "1":
            self._login()
        elif choice == "2":
            self._login_visitor()
        elif choice == "3":
            self._register()
        elif choice == "4":
            self.running = False
        else:
            print("Invalid choice. Please try again.")
    
    def _show_main_menu(self):
        """Show main menu for logged-in users"""
        if self.is_visitor:
            print(f"\n--- Main Menu (Visitor: {self.username}) ---")
        else:
            print(f"\n--- Main Menu (User: {self.username}) ---")
        
        print("1. List available channels")
        print("2. Join a channel")
        
        if not self.is_visitor:
            print("3. Create a new channel")
            print("4. Host one of my channels")
            print("5. Set status (online/invisible)")
        
        print("9. Logout")
        
        if self.is_visitor:
            choice = input("\nEnter your choice (1-2, 9): ")
        else:
            choice = input("\nEnter your choice (1-5, 9): ")
        
        if choice == "1":
            self._list_channels()
        elif choice == "2":
            self._join_channel_menu()
        elif choice == "3" and not self.is_visitor:
            self._create_channel_menu()
        elif choice == "4" and not self.is_visitor:
            self._host_channel_menu()
        elif choice == "5" and not self.is_visitor:
            self._set_status_menu()
        elif choice == "9":
            self.logout()
        else:
            print("Invalid choice. Please try again.")
    
    def _login(self):
        """Login as a registered user"""
        username = input("Username: ")
        password = getpass.getpass("Password: ")
        
        # Send login request to server
        request = {
            "type": "AUTH",
            "username": username,
            "password": password
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.token = response.get("token")
            self.username = username
            self.is_visitor = False
            print(f"Login successful. Welcome, {username}!")
            
            # Initialize peer
            self._initialize_peer()
        else:
            print(f"Login failed: {response.get('message')}")
    
    def _login_visitor(self):
        """Login as a visitor"""
        visitor_name = input("Enter your visitor name: ")
        
        # Send visitor login request to server
        request = {
            "type": "VISITOR",
            "name": visitor_name
        }
        
        response = self._send_to_central_server(request)
        
        if response.get("success"):
            self.token = response.get("token")
            self.username = visitor_name
            self.is_visitor = True
            print(f"Visitor login successful. Welcome, {visitor_name}!")
            
            # Initialize peer
            self._initialize_peer()
        else:
            print(f"Visitor login failed: {response.get('message')}")
    
    def _register(self, username, password, email=""):
        """Register a new user"""
        # Register using authentication system
        success, message = auth.register_user(username, password, email)
        
        if success:
            print(f"Registration successful: {message}")
        else:
            print(f"Registration failed: {message}")
            
        return success, message
    
    def _initialize_peer(self):
        """Initialize the peer component"""
        # Find an available port
        peer_port = self._find_available_port(8001, 9000)
        
        if not peer_port:
            print("Failed to find an available port for peer communication.")
            return False
        
        # Get local IP
        local_ip = self._get_local_ip()
        
        # Create peer
        self.peer = Peer(
            self.username, 
            local_ip, 
            peer_port,
            self.central_server_host,
            self.central_server_port
        )
        
        # Set visitor flag
        self.peer.set_is_visitor(self.is_visitor)
        
        # Start peer
        if self.peer.start():
            # Register with central server
            if self.peer.register_with_central_server(self.token):
                print(f"Peer server started on {local_ip}:{peer_port}")
                return True
            else:
                print("Failed to register with central server.")
                self.peer.stop()
                self.peer = None
                return False
        else:
            print("Failed to start peer server.")
            self.peer = None
            return False
    
    def _find_available_port(self, start_port, end_port):
        """Find an available port in the given range"""
        for port in range(start_port, end_port + 1):
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(0.1)
            try:
                test_socket.bind(('', port))
                test_socket.close()
                return port
            except socket.error:
                continue
        return None
    
    def _get_local_ip(self):
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
    
    def _list_channels(self):
        """List available channels"""
        channels = db.list_channels()
        if not channels:
            return {}  # Ensure an empty dictionary is returned if no channels are available
        return channels
    
    def _join_channel_menu(self):
        """Menu for joining a channel"""
        channel_name = input("Enter channel name to join: ")
        
        # Check if channel exists
        channel = db.get_channel(channel_name)
        if not channel:
            print(f"Channel '{channel_name}' does not exist.")
            return
        
        # Add user to channel in database if not a visitor
        if not self.is_visitor:
            db.join_channel(channel_name, self.username)
        
        # Join channel at peer level
        if self.peer.join_channel(channel_name):
            self.current_channel = channel_name
            print(f"Joined channel: {channel_name}")
            self._enter_chat_mode(channel_name)
        else:
            print(f"Failed to join channel: {channel_name}")
    
    def _create_channel_menu(self):
        """Menu for creating a new channel"""
        if self.is_visitor:
            print("Visitors cannot create channels.")
            return
        
        channel_name = input("Enter channel name: ")
        description = input("Enter channel description (optional): ")
        
        # Create channel
        if self._create_channel(channel_name, description):
            print(f"Channel '{channel_name}' created successfully.")
        else:
            print(f"Failed to create channel '{channel_name}' (it may already exist).")
    
    def _create_channel(self, name, desc):
        """Create a new channel"""
        if self.is_visitor:
            print("Visitors cannot create channels.")
            return False

        # Create channel in database
        success = db.create_channel(name, self.username, desc)

        if success:
            print(f"Channel '{name}' created successfully.")
            return True
        else:
            print(f"Failed to create channel '{name}' (it may already exist).")
            return False
    
    def _host_channel_menu(self):
        """Menu for hosting a channel"""
        if self.is_visitor:
            print("Visitors cannot host channels.")
            return
        
        # Get channels owned by this user
        users = db.get_user(self.username)
        if not users:
            print("User information not found.")
            return
        
        owned_channels = users.get("channels_owned", [])
        
        if not owned_channels:
            print("You don't own any channels.")
            return
        
        print("\n--- Your Channels ---")
        for i, channel in enumerate(owned_channels, 1):
            print(f"{i}. {channel}")
        
        try:
            choice = int(input("\nEnter channel number to host (0 to cancel): "))
            
            if choice == 0:
                return
            
            if choice < 1 or choice > len(owned_channels):
                print("Invalid choice.")
                return
            
            channel_name = owned_channels[choice - 1]
            
            # Host the channel
            if self.peer.host_channel(channel_name):
                print(f"Now hosting channel: {channel_name}")
            else:
                print(f"Failed to host channel: {channel_name}")
                
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    def _set_status_menu(self):
        """Menu for setting user status"""
        if self.is_visitor:
            print("Visitors cannot change status.")
            return
        
        print("\n--- Set Status ---")
        print("1. Online")
        print("2. Invisible")
        
        choice = input("\nEnter your choice (1-2): ")
        
        status = None
        if choice == "1":
            status = "online"
        elif choice == "2":
            status = "invisible"
        else:
            print("Invalid choice.")
            return
        
        # Send status update request
        request = {
            "type": "STATUS",
            "token": self.token,
            "status": status
        }
        
        response = auth.set_user_status(self.token, status)
        
        if response[0]:
            print(f"Status updated to {status}.")
        else:
            print(f"Failed to update status: {response[1]}")
    
    def _enter_chat_mode(self, channel_name):
        """Enter chat mode for a specific channel"""
        print(f"\nEntered chat mode for channel: {channel_name}")
        print("Type your message and press Enter to send.")
        print("Type /exit to leave the channel, /help for more commands.")
        
        # Get message history
        messages = self.get_channel_history(channel_name, since_id=0, limit=50)
        
        # Display recent messages
        if messages:
            print("\n--- Recent Messages ---")
            # Sort messages by id to ensure chronological order
            sorted_messages = sorted(messages, key=lambda x: x.get('id', 0))
            # Show the most recent messages (last 10)
            recent_messages = sorted_messages[-10:] if len(sorted_messages) > 10 else sorted_messages
            for msg in recent_messages:
                try:
                    timestamp = msg["timestamp"].split("T")[1].split(".")[0]  # Extract time
                    print(f"[{timestamp}] {msg['username']}: {msg['content']}")
                except Exception as e:
                    print(f"Error formatting message: {e}")
                    continue
        else:
            print("\nNo message history available.")
        
        # Start chat input loop
        self._chat_input_loop(channel_name)
    
    def _chat_input_loop(self, channel_name):
        """Handle user input in chat mode"""
        while self.running and self.current_channel == channel_name:
            try:
                message = input("> ")
                
                # Handle commands
                if message.startswith("/"):
                    self._handle_chat_command(message, channel_name)
                    continue
                
                # Skip empty messages
                if not message.strip():
                    continue
                
                # Send message
                if self.peer.send_message(channel_name, message):
                    # Message sent successfully, no need to print anything
                    pass
                else:
                    print("Failed to send message.")
                
            except EOFError:
                # Handle Ctrl+D
                print("\nLeaving channel...")
                self.current_channel = None
                break
            except Exception as e:
                print(f"Error in chat mode: {e}")
    
    def _handle_chat_command(self, command, channel_name):
        """Handle chat commands"""
        cmd = command.lower().split()[0]
        
        if cmd == "/exit":
            print("Leaving channel...")
            if self.peer:
                self.peer.leave_channel(channel_name)
            self.current_channel = None
        
        elif cmd == "/help":
            print("\n--- Chat Commands ---")
            print("/exit       - Leave the current channel")
            print("/history    - Show more message history")
            print("/users      - Show users in the channel")
            print("/help       - Show this help message")
        
        elif cmd == "/history":
            # Get more message history
            messages = self.peer.get_channel_history(channel_name, limit=30)
            
            if messages:
                print("\n--- Message History ---")
                for msg in messages:
                    timestamp = msg["timestamp"].split("T")[1].split(".")[0]  # Extract time
                    print(f"[{timestamp}] {msg['username']}: {msg['content']}")
            else:
                print("No message history available.")
        
        elif cmd == "/users":
            # Get channel info
            channel = db.get_channel(channel_name)
            
            if channel:
                print("\n--- Channel Users ---")
                for username in channel["members"]:
                    user = db.get_user(username)
                    status = "unknown"
                    if user:
                        status = user.get("status", "offline")
                    
                    print(f"{username} - {status}")
            else:
                print("Unable to retrieve channel information.")
        
        else:
            print(f"Unknown command: {cmd}")
            print("Type /help for a list of commands.")
    
    def logout(self):
        """Logout the current user"""
        if not self.token:
            return
        
        # Stop peer
        if self.peer:
            self.peer.stop()
            self.peer = None
        
        # Send logout request to server
        request = {
            "type": "LOGOUT",
            "token": self.token
        }
        
        response = self._send_to_central_server(request)
        
        # Reset client state
        self.token = None
        self.username = None
        self.is_visitor = False
        self.current_channel = None
        
        print("Logged out successfully.")
    
    def join_channel(self, channel_name):
        """Join a channel hosted by another peer or the central server"""
        # Check if the channel exists in the database
        channel = db.get_channel(channel_name)
        if not channel:
            print(f"Channel '{channel_name}' does not exist.")
            return False

        # Add user to the channel in the database if not a visitor
        if not self.is_visitor:
            db.join_channel(channel_name, self.username)

        # Attempt to join the channel through the central server
        request = {
            "type": "JOIN_CHANNEL",
            "token": self.token,
            "channel": channel_name
        }
        response = self._send_to_central_server(request)

        if response.get("success"):
            print(f"Successfully joined channel: {channel_name} via central server.")
            return True

        # Fallback to peer-to-peer hosting if central server fails
        if self.peer.join_channel(channel_name):
            print(f"Successfully joined channel: {channel_name} via peer-to-peer.")
            return True
        else:
            print(f"Failed to join channel: {channel_name}")
            return False

    def get_channel_history(self, channel_name, since_id=0, limit=50):
        """Get message history for a channel"""
        # Attempt to get history from the central server
        request = {
            "type": "GET_HISTORY",
            "token": self.token,
            "channel": channel_name,
            "since_id": since_id,
            "limit": limit
        }
        response = self._send_to_central_server(request)

        # Debug print
        # print(f"ChatClient get_channel_history response: {response}")

        if response.get("success"):
            messages = response.get("messages", [])
            # print(f"Retrieved {len(messages)} messages for {channel_name}")
            return messages
        else:
            print(f"Failed to get history: {response.get('message')}")
            return []

    def send_message(self, channel_name, content):
        """Send a message to a channel"""
        # Check if user is a visitor (view-only)
        if self.is_visitor:
            print("Visitors cannot send messages - view-only mode")
            return False
            
        # Attempt to send the message through the central server
        request = {
            "type": "SEND_MESSAGE",
            "token": self.token,
            "channel": channel_name,
            "content": content
        }
        response = self._send_to_central_server(request)

        if response.get("success"):
            print(f"Message sent to channel {channel_name}")
            return True
        else:
            print(f"Failed to send message: {response.get('message')}")
            return False

    def get_online_users(self):
        """Get a list of users currently online"""
        if not self.token:
            print("You need to be logged in to see online users.")
            return []
        
        # Send request to the server
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

    def start_stream(self, channel_name):
        """Start a stream in a channel"""
        request = {
            "type": "STREAM_START",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        if response.get("success"):
            print(f"Started stream in channel {channel_name}")
            return True
        else:
            print(f"Failed to start stream: {response.get('message')}")
            return False
    
    def end_stream(self, channel_name):
        """End a stream in a channel"""
        request = {
            "type": "STREAM_END",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        if response.get("success"):
            print(f"Ended stream in channel {channel_name}")
            return True
        else:
            print(f"Failed to end stream: {response.get('message')}")
            return False
    
    def join_stream(self, channel_name):
        """Join a stream in a channel"""
        request = {
            "type": "STREAM_JOIN",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        if response.get("success"):
            print(f"Joined stream in channel {channel_name}")
            return response.get("stream_info")
        else:
            print(f"Failed to join stream: {response.get('message')}")
            return None
    
    def leave_stream(self, channel_name):
        """Leave a stream in a channel"""
        request = {
            "type": "STREAM_LEAVE",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        if response.get("success"):
            print(f"Left stream in channel {channel_name}")
            return True
        else:
            print(f"Failed to leave stream: {response.get('message')}")
            return False

    def get_stream_info(self, channel_name):
        """Get information about an active stream in a channel"""
        request = {
            "type": "GET_STREAM_INFO",
            "token": self.token,
            "channel": channel_name
        }
        
        response = self._send_to_central_server(request)
        if response.get("success"):
            return response.get("stream_info")
        return None

    def get_channel(self, channel_name):
        """Get channel information from the database"""
        # Get channel info from database
        channel = db.get_channel(channel_name)
        if not channel:
            print(f"Channel '{channel_name}' not found")
            return None
            
        return channel

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                prog='Chat Client',
                description='Discord-like chat application client',
                epilog='Supports both client-server and P2P communication')
    
    parser.add_argument('--server-host', default='127.0.0.1')
    parser.add_argument('--server-port', type=int, default=8000)
    
    args = parser.parse_args()
    
    client = ChatClient(args.server_host, args.server_port)
    client.start()