#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
from datetime import datetime
from chat_client import ChatClient
import time
import socket
import av
import asyncio
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceServer
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
import cv2  # Added import for OpenCV

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

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Discord but without rd")
        self.root.geometry("1200x700")  # Made window wider for stream
        
        # Set color scheme first
        self.colors = {
            'bg': '#36393F',  # Discord dark background
            'light_bg': '#40444B',  # Discord lighter background
            'accent': '#7289DA',  # Discord blurple
            'text': '#FFFFFF',  # White text
            'secondary_text': '#B9BBBE',  # Discord secondary text
            'input_bg': '#40444B',  # Discord input background
            'online': '#43B581',    # Discord online status color
            'invisible': '#747F8D'  # Discord invisible status color
        }
        
        # Add WebRTC-related attributes
        '''
        self.pc = None  # RTCPeerConnection
        self.is_streaming = False
        self.stream_track = None
        self.viewers = {}  # Dictionary of peer connections for viewers
        self.stream_start_time = None  # For chat message timestamps
        self.video_recorder = None
        self.local_video = None
        
        # Stream window
        self.stream_window = None
        self.stream_canvas = None
        '''
        
        # Initialize chat display after colors are defined
        self.chat_display = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg=self.colors['light_bg'],
            fg=self.colors['text'],
            font=('Helvetica', 10),
            state=tk.DISABLED
        )
        
        # Configure root window background
        self.root.configure(bg=self.colors['bg'])
        
        # Configure styles
        self.style = ttk.Style()
        self.style.configure('Main.TFrame', background=self.colors['bg'])
        self.style.configure('Channel.TFrame', background=self.colors['light_bg'])
        self.style.configure('Discord.TLabel', 
                           background=self.colors['bg'],
                           foreground=self.colors['text'])
        self.style.configure('Discord.TButton',
                           background=self.colors['accent'],
                           foreground=self.colors['text'])
        self.style.configure('Discord.TEntry',
                           fieldbackground=self.colors['input_bg'],
                           foreground=self.colors['text'])
        
        # Initialize chat client with auto-detected server IP
        self.chat_client = ChatClient(get_local_ip(), 8000)
        self.current_channel = None
        self.message_update_thread = None
        self.running = False
        self.last_message_ids = {}  # Track last message ID per channel
        self.user_status = "online"  # Default status
        
        self._create_gui()

    def _create_gui(self):
        # Create main container with Discord styling
        self.main_container = ttk.Frame(self.root, style='Main.TFrame')
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Create and show login frame initially
        self.show_login_frame()

    def show_login_frame(self):
        # Clear main container
        for widget in self.main_container.winfo_children():
            widget.destroy()
        
        # Login frame with Discord styling
        login_frame = ttk.Frame(self.main_container, style='Main.TFrame')
        login_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Center the login content
        center_frame = ttk.Frame(login_frame, style='Main.TFrame')
        center_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Title
        title_label = ttk.Label(center_frame, 
                              text="Welcome back!",
                              style='Discord.TLabel',
                              font=('Helvetica', 24, 'bold'))
        title_label.pack(pady=20)
        
        subtitle_label = ttk.Label(center_frame,
                                 text="We're so excited to see you again!",
                                 style='Discord.TLabel',
                                 font=('Helvetica', 14))
        subtitle_label.pack(pady=(0, 20))
        
        # Username
        ttk.Label(center_frame, text="USERNAME", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.username_entry = ttk.Entry(center_frame, width=30, style='Discord.TEntry')
        self.username_entry.pack(pady=(0, 15))
        
        # Password
        ttk.Label(center_frame, text="PASSWORD", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.password_entry = ttk.Entry(center_frame, show="•", width=30, style='Discord.TEntry')
        self.password_entry.pack(pady=(0, 20))
        
        # Buttons with Discord styling
        login_button = tk.Button(center_frame, 
                               text="Login",
                               command=self._handle_login,
                               bg=self.colors['accent'],
                               fg=self.colors['text'],
                               font=('Helvetica', 12),
                               relief=tk.FLAT,
                               padx=20,
                               pady=10)
        login_button.pack(pady=5, fill=tk.X)
        
        visitor_button = tk.Button(center_frame,
                                 text="Enter as Visitor",
                                 command=self._handle_visitor_login,
                                 bg=self.colors['light_bg'],
                                 fg=self.colors['text'],
                                 font=('Helvetica', 12),
                                 relief=tk.FLAT,
                                 padx=20,
                                 pady=10)
        visitor_button.pack(pady=5, fill=tk.X)
        
        register_button = tk.Button(center_frame,
                                  text="Register",
                                  command=self.show_register_frame,
                                  bg=self.colors['light_bg'],
                                  fg=self.colors['text'],
                                  font=('Helvetica', 12),
                                  relief=tk.FLAT,
                                  padx=20,
                                  pady=10)
        register_button.pack(pady=5, fill=tk.X)

    def show_register_frame(self):
        # Clear main container
        for widget in self.main_container.winfo_children():
            widget.destroy()
        
        # Register frame with Discord styling
        register_frame = ttk.Frame(self.main_container, style='Main.TFrame')
        register_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Center the register content
        center_frame = ttk.Frame(register_frame, style='Main.TFrame')
        center_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Title
        title_label = ttk.Label(center_frame, 
                              text="Create an account",
                              style='Discord.TLabel',
                              font=('Helvetica', 24, 'bold'))
        title_label.pack(pady=20)
        
        # Username
        ttk.Label(center_frame, text="USERNAME", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.reg_username_entry = ttk.Entry(center_frame, width=30, style='Discord.TEntry')
        self.reg_username_entry.pack(pady=(0, 15))
        
        # Password
        ttk.Label(center_frame, text="PASSWORD", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.reg_password_entry = ttk.Entry(center_frame, show="•", width=30, style='Discord.TEntry')
        self.reg_password_entry.pack(pady=(0, 15))
        
        # Confirm Password
        ttk.Label(center_frame, text="CONFIRM PASSWORD", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.reg_confirm_entry = ttk.Entry(center_frame, show="•", width=30, style='Discord.TEntry')
        self.reg_confirm_entry.pack(pady=(0, 15))
        
        # Email
        ttk.Label(center_frame, text="EMAIL (optional)", 
                 style='Discord.TLabel',
                 font=('Helvetica', 12, 'bold')).pack(pady=(0, 5))
        self.reg_email_entry = ttk.Entry(center_frame, width=30, style='Discord.TEntry')
        self.reg_email_entry.pack(pady=(0, 20))
        
        # Buttons with Discord styling
        register_button = tk.Button(center_frame, 
                                  text="Register",
                                  command=self._handle_register,
                                  bg=self.colors['accent'],
                                  fg=self.colors['text'],
                                  font=('Helvetica', 12),
                                  relief=tk.FLAT,
                                  padx=20,
                                  pady=10)
        register_button.pack(pady=5, fill=tk.X)
        
        back_button = tk.Button(center_frame,
                              text="Back to Login",
                              command=self.show_login_frame,
                              bg=self.colors['light_bg'],
                              fg=self.colors['text'],
                              font=('Helvetica', 12),
                              relief=tk.FLAT,
                              padx=20,
                              pady=10)
        back_button.pack(pady=5, fill=tk.X)

    def show_main_frame(self):
        # Clear main container
        for widget in self.main_container.winfo_children():
            widget.destroy()
        
        # Create main layout with Discord styling
        # Left sidebar (channel list)
        left_frame = ttk.Frame(self.main_container, style='Channel.TFrame')
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0, expand=False)
        
        # User info with status
        user_frame = ttk.Frame(left_frame, style='Channel.TFrame')
        user_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Status indicator canvas (circle)
        status_canvas = tk.Canvas(user_frame, width=12, height=12, 
                                background=self.colors['light_bg'],
                                highlightthickness=0)
        status_canvas.pack(side=tk.LEFT, padx=(0, 5))
        
        # Show user status with visitor indicator if applicable
        user_label_text = f"{self.chat_client.username}"
        if self.chat_client.is_visitor:
            user_label_text += " (Visitor - View Only)"
            # Draw status circle (always online for visitors)
            status_canvas.create_oval(2, 2, 10, 10, fill=self.colors['online'], outline="")
        else:
            # Get current status and draw appropriate color
            self.user_status = self._get_user_status()
            status_color = self.colors['online'] if self.user_status == "online" else self.colors['invisible']
            if self.user_status == "offline":
                status_color = "#747F8D"  # Gray for offline
            status_canvas.create_oval(2, 2, 10, 10, fill=status_color, outline="")
            
            # Add status text
            user_label_text += f" ({self.user_status})"
        
        user_label = ttk.Label(user_frame, 
                             text=user_label_text,
                             style='Discord.TLabel',
                             font=('Helvetica', 12, 'bold'))
        user_label.pack(side=tk.LEFT)
        
        # Add status change button for authenticated users
        if not self.chat_client.is_visitor:
            status_btn = tk.Button(user_frame,
                                text="Change Status",
                                command=self._show_status_dialog,
                                bg=self.colors['light_bg'],
                                fg=self.colors['text'],
                                font=('Helvetica', 12),
                                relief=tk.FLAT)
            status_btn.pack(side=tk.RIGHT)
        
        # Add sync status indicator
        self.sync_label = ttk.Label(left_frame, 
                                  text="",
                                  style='Discord.TLabel',
                                  font=('Helvetica', 8))
        self.sync_label.pack(padx=10, pady=2)
        
        # Channels section
        channels_label = ttk.Label(left_frame, 
                                 text="CHANNELS",
                                 style='Discord.TLabel',
                                 font=('Helvetica', 12, 'bold'))
        channels_label.pack(padx=10, pady=(20, 10), anchor=tk.W)
        
        # Channel controls
        if not self.chat_client.is_visitor:
            create_btn = tk.Button(left_frame,
                                 text="➕ Create Channel",
                                 command=self._show_create_channel_dialog,
                                 bg=self.colors['light_bg'],
                                 fg=self.colors['text'],
                                 font=('Helvetica', 10),
                                 relief=tk.FLAT)
            create_btn.pack(fill=tk.X, padx=10, pady=2)
        
        # Channel list with Discord styling
        self.channel_listbox = tk.Listbox(left_frame,
                                        bg=self.colors['light_bg'],
                                        fg=self.colors['text'],
                                        selectbackground=self.colors['accent'],
                                        selectforeground=self.colors['text'],
                                        font=('Helvetica', 11),
                                        relief=tk.FLAT,
                                        borderwidth=0)
        self.channel_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.channel_listbox.bind('<Double-Button-1>', lambda e: self._join_selected_channel())
        
        # Online Users Section
        online_users_label = ttk.Label(left_frame, 
                                     text="ONLINE USERS",
                                     style='Discord.TLabel',
                                     font=('Helvetica', 12, 'bold'))
        online_users_label.pack(padx=10, pady=(15, 5), anchor=tk.W)
        
        # Online users list
        self.online_users_frame = ttk.Frame(left_frame, style='Channel.TFrame')
        self.online_users_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=False)
        
        # Create a scrollable frame for online users
        online_users_canvas = tk.Canvas(self.online_users_frame, 
                                      bg=self.colors['light_bg'],
                                      highlightthickness=0)
        online_users_scrollbar = ttk.Scrollbar(self.online_users_frame, 
                                            orient="vertical", 
                                            command=online_users_canvas.yview)
        online_users_scrollable_frame = ttk.Frame(online_users_canvas, style='Channel.TFrame')
        
        online_users_scrollable_frame.bind(
            "<Configure>",
            lambda e: online_users_canvas.configure(
                scrollregion=online_users_canvas.bbox("all")
            )
        )
        
        online_users_canvas.create_window((0, 0), window=online_users_scrollable_frame, anchor="nw")
        online_users_canvas.configure(yscrollcommand=online_users_scrollbar.set)
        
        online_users_canvas.pack(side="left", fill="both", expand=True)
        online_users_scrollbar.pack(side="right", fill="y")
        
        # Store reference to the scrollable frame
        self.online_users_scrollable_frame = online_users_scrollable_frame
        
        # Refresh button for online users
        refresh_btn = tk.Button(left_frame,
                              text="🔄 Refresh Online Users",
                              command=self._refresh_online_users,
                              bg=self.colors['light_bg'],
                              fg=self.colors['text'],
                              font=('Helvetica', 8),
                              relief=tk.FLAT)
        refresh_btn.pack(fill=tk.X, padx=10, pady=2)
        
        # Initially populate online users list
        self._refresh_online_users()
        
        # Logout button at bottom
        logout_btn = tk.Button(left_frame,
                             text="Logout",
                             command=self._handle_logout,
                             bg=self.colors['light_bg'],
                             fg=self.colors['text'],
                             font=('Helvetica', 10),
                             relief=tk.FLAT)
        logout_btn.pack(fill=tk.X, padx=10, pady=10)
        
        # Right side (chat area)
        right_frame = ttk.Frame(self.main_container, style='Main.TFrame')
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Chat frame
        chat_frame = ttk.Frame(right_frame, style='Main.TFrame')
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Initialize chat display with proper packing
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg=self.colors['light_bg'],
            fg=self.colors['text'],
            font=('Helvetica', 10),
            state=tk.DISABLED,
            height=20
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Message input frame
        message_frame = ttk.Frame(chat_frame, style='Main.TFrame')
        message_frame.pack(fill=tk.X, pady=5)
        
        # Message input field
        self.message_entry = ttk.Entry(message_frame, style='Discord.TEntry')
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Send button
        send_btn = tk.Button(message_frame,
                           text="Send",
                           command=self._send_message,
                           bg=self.colors['accent'],
                           fg=self.colors['text'],
                           font=('Helvetica', 10),
                           relief=tk.FLAT)
        send_btn.pack(side=tk.RIGHT)
        
        # Bind Enter key to send message
        self.message_entry.bind('<Return>', lambda e: self._send_message())
        
        # Refresh channels list
        self._refresh_channels()
        
        # Start online users refresh thread
        if not hasattr(self, 'online_users_update_thread') or not self.online_users_update_thread.is_alive():
            self.online_users_update_thread = threading.Thread(target=self._update_online_users)
            self.online_users_update_thread.daemon = True
            self.online_users_update_thread.start()

    def _handle_login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        # Use existing login logic from chat client
        request = {
            "type": "AUTH",
            "username": username,
            "password": password
        }
        
        response = self.chat_client._send_to_central_server(request)
        
        if response.get("success"):
            self.chat_client.token = response.get("token")
            self.chat_client.username = username
            self.chat_client.is_visitor = False
            
            # Initialize peer
            if self.chat_client._initialize_peer():
                self.running = True
                self.show_main_frame()
            else:
                messagebox.showerror("Error", "Failed to initialize peer connection")
        else:
            messagebox.showerror("Login Failed", response.get("message", "Invalid username or password"))
    
    def _handle_visitor_login(self):
        visitor_name = self.username_entry.get()
        if not visitor_name:
            messagebox.showerror("Error", "Please enter a visitor name")
            return
        
        request = {
            "type": "VISITOR",
            "name": visitor_name
        }
        
        response = self.chat_client._send_to_central_server(request)
        
        if response.get("success"):
            self.chat_client.token = response.get("token")
            self.chat_client.username = visitor_name
            self.chat_client.is_visitor = True
            
            # Initialize peer
            if self.chat_client._initialize_peer():
                self.running = True
                self.show_main_frame()
            else:
                messagebox.showerror("Error", "Failed to initialize peer connection")
        else:
            messagebox.showerror("Login Failed", response.get("message"))
    
    def _handle_register(self):
        username = self.reg_username_entry.get()
        password = self.reg_password_entry.get()
        confirm = self.reg_confirm_entry.get()
        email = self.reg_email_entry.get()
        
        if password != confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return
        
        success, message = self.chat_client._register(username, password, email)
        
        if success:
            messagebox.showinfo("Success", message)
            self.show_login_frame()
        else:
            messagebox.showerror("Registration Failed", message)
    
    def _handle_logout(self):
        if self.chat_client:
            self.chat_client.logout()
        self.running = False
        self.last_message_ids.clear()  # Clear message history tracking
        self.show_login_frame()
    
    def _refresh_channels(self):
        channels = self.chat_client._list_channels()
        self.channel_listbox.delete(0, tk.END)
        for name, info in channels.items():
            self.channel_listbox.insert(tk.END, f"{name} ({info['owner']})")
    
    def _show_create_channel_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Channel")
        dialog.geometry("300x200")
        
        ttk.Label(dialog, text="Channel Name:").pack(pady=5)
        name_entry = ttk.Entry(dialog)
        name_entry.pack(pady=5)
        
        ttk.Label(dialog, text="Description:").pack(pady=5)
        desc_entry = ttk.Entry(dialog)
        desc_entry.pack(pady=5)
        
        def create():
            name = name_entry.get()
            desc = desc_entry.get()
            if self.chat_client._create_channel(name, desc):
                self._refresh_channels()
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Failed to create channel")
        
        ttk.Button(dialog, text="Create", command=create).pack(pady=20)
    
    def _join_selected_channel(self):
        selection = self.channel_listbox.curselection()
        if not selection:
            return

        channel_text = self.channel_listbox.get(selection[0])
        channel_name = channel_text.split(" (")[0]

        if self.chat_client.join_channel(channel_name):
            self.current_channel = channel_name
            
            # Ensure chat display exists
            if not hasattr(self, 'chat_display') or not self.chat_display.winfo_exists():
                # Create chat frame if it doesn't exist
                chat_frame = ttk.Frame(self.main_container, style='Channel.TFrame')
                chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                self.chat_display = scrolledtext.ScrolledText(
                    chat_frame,
                    wrap=tk.WORD,
                    bg=self.colors['light_bg'],
                    fg=self.colors['text'],
                    font=('Helvetica', 10),
                    state=tk.DISABLED,
                    height=20
                )
                self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Clear display and reset message tracking
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.last_message_ids[channel_name] = 0

            # Get ALL message history initially (no limit)
            messages = self.chat_client.get_channel_history(channel_name, since_id=0, limit=0)
            
            # Debug print
            print(f"Retrieved {len(messages) if messages else 0} messages for {channel_name}")

            if messages:
                # Insert join notification
                join_msg = f"\n=== Joined channel: {channel_name} ===\n\n"
                self.chat_display.insert(tk.END, join_msg)

                # Insert ALL message history
                for msg in sorted(messages, key=lambda x: x.get('id', 0)):
                    try:
                        timestamp = msg["timestamp"].split("T")[1].split(".")[0]  # Extract time
                        formatted_msg = f"[{timestamp}] {msg['username']}: {msg['content']}\n"
                        self.chat_display.insert(tk.END, formatted_msg)
                        if "id" in msg:
                            self.last_message_ids[channel_name] = max(
                                self.last_message_ids[channel_name],
                                msg["id"]
                            )
                    except Exception as e:
                        print(f"Error formatting message: {e}, message: {msg}")
                        continue
            else:
                self.chat_display.insert(tk.END, f"\n=== Joined channel: {channel_name} ===\nNo messages yet.\n")

            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)

            # Start message update thread if not already running
            if self.message_update_thread is None or not self.message_update_thread.is_alive():
                self.message_update_thread = threading.Thread(target=self._update_messages)
                self.message_update_thread.daemon = True
                self.message_update_thread.start()
        else:
            messagebox.showerror("Error", f"Failed to join channel: {channel_name}")

    def _send_message(self):
        if not self.current_channel:
            messagebox.showwarning("Warning", "Please join a channel first")
            return
        
        message = self.message_entry.get()
        if not message:
            return
            
        # Handle sending message in offline mode
        if self.chat_client.peer.is_offline:
            # Store in offline content
            if self.current_channel not in self.chat_client.peer.offline_content:
                self.chat_client.peer.offline_content[self.current_channel] = []
            
            timestamp = datetime.now().isoformat()
            offline_msg = {
                "content": message,
                "timestamp": timestamp
            }
            self.chat_client.peer.offline_content[self.current_channel].append(offline_msg)
            
            # Show in chat with offline indicator
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, 
                f"[{timestamp.split('T')[1].split('.')[0]}] {self.chat_client.username} (offline): {message}\n"
            )
            self.chat_display.see(tk.END)
            self.chat_display.config(state=tk.DISABLED)
            
            self.message_entry.delete(0, tk.END)
            self._update_sync_status("Message saved - will sync when online")
            return
            
        # Normal online sending
        if self.chat_client.send_message(self.current_channel, message):
            self.message_entry.delete(0, tk.END)
        else:
            messagebox.showerror("Error", "Failed to send message")
    
    def _update_messages(self):
        """Periodically check for new messages in the current channel"""
        while self.running:
            try:
                if self.current_channel:
                    last_id = self.last_message_ids.get(self.current_channel, 0)
                    messages = self.chat_client.get_channel_history(
                        self.current_channel, 
                        since_id=last_id
                    )
                    
                    if messages:
                        self.chat_display.config(state=tk.NORMAL)
                        for msg in messages:
                            try:
                                timestamp = msg["timestamp"].split("T")[1].split(".")[0]  # Extract time
                                formatted_msg = f"[{timestamp}] {msg['username']}: {msg['content']}\n"
                                self.chat_display.insert(tk.END, formatted_msg)
                                if "id" in msg:
                                    self.last_message_ids[self.current_channel] = max(
                                        self.last_message_ids[self.current_channel],
                                        msg["id"]
                                    )
                            except Exception as e:
                                print(f"Error formatting message: {e}, message: {msg}")
                                continue
                        self.chat_display.see(tk.END)
                        self.chat_display.config(state=tk.DISABLED)
            except Exception as e:
                print(f"Error in update messages: {e}")
                
            time.sleep(1)
    
    def _show_status_dialog(self):
        """Show dialog for changing user status"""
        if self.chat_client.is_visitor:
            messagebox.showinfo("Status", "Visitors cannot change their status")
            return
            
        dialog = tk.Toplevel(self.root)
        dialog.title("Change Status")
        dialog.geometry("300x200")  # Made slightly taller for offline option
        dialog.configure(bg=self.colors['bg'])
        
        ttk.Label(dialog, 
                text="Select Status:", 
                style='Discord.TLabel',
                font=('Helvetica', 12, 'bold')).pack(pady=10)
        
        status_var = tk.StringVar(value=self.user_status)
        
        # Status options frame
        options_frame = ttk.Frame(dialog, style='Main.TFrame')
        options_frame.pack(pady=5)
        
        # Create a frame for the status description/feedback
        feedback_frame = ttk.Frame(dialog, style='Main.TFrame')
        feedback_frame.pack(pady=5, fill=tk.X, padx=10)
        
        # Create a label to show the selected status description
        status_description = tk.StringVar()
        if self.user_status == "online":
            status_description.set("You appear as online to others")
        elif self.user_status == "offline":
            status_description.set("You appear as offline and messages will be cached locally")
        else:
            status_description.set("You appear as offline but have full functionality")
            
        status_feedback = ttk.Label(feedback_frame,
                                  textvariable=status_description,
                                  style='Discord.TLabel',
                                  font=('Helvetica', 9, 'italic'))
        status_feedback.pack(fill=tk.X)
        
        # Online option
        online_frame = ttk.Frame(options_frame, style='Main.TFrame')
        online_frame.pack(fill=tk.X, pady=2)
        
        online_canvas = tk.Canvas(online_frame, width=12, height=12, 
                                background=self.colors['bg'],
                                highlightthickness=0)
        online_canvas.pack(side=tk.LEFT, padx=5)
        online_canvas.create_oval(2, 2, 10, 10, fill=self.colors['online'], outline="")
        
        online_select_frame = tk.Frame(online_frame, bg=self.colors['bg'])
        online_select_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        online_radio = ttk.Radiobutton(online_select_frame, 
                                      text="Online",
                                      variable=status_var, 
                                      value="online",
                                      style='Discord.TLabel',
                                      command=lambda: status_description.set("You appear as online to others"))
        online_radio.pack(side=tk.LEFT)
        
        # Offline option
        offline_frame = ttk.Frame(options_frame, style='Main.TFrame')
        offline_frame.pack(fill=tk.X, pady=2)
        
        offline_canvas = tk.Canvas(offline_frame, width=12, height=12, 
                                 background=self.colors['bg'],
                                 highlightthickness=0)
        offline_canvas.pack(side=tk.LEFT, padx=5)
        offline_canvas.create_oval(2, 2, 10, 10, fill="#747F8D", outline="")
        
        offline_select_frame = tk.Frame(offline_frame, bg=self.colors['bg'])
        offline_select_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        offline_radio = ttk.Radiobutton(offline_select_frame, 
                                      text="Offline",
                                      variable=status_var, 
                                      value="offline",
                                      style='Discord.TLabel',
                                      command=lambda: status_description.set("You appear as offline and messages will be cached locally"))
        offline_radio.pack(side=tk.LEFT)
        
        # Invisible option
        invisible_frame = ttk.Frame(options_frame, style='Main.TFrame')
        invisible_frame.pack(fill=tk.X, pady=2)
        
        invisible_canvas = tk.Canvas(invisible_frame, width=12, height=12, 
                                   background=self.colors['bg'],
                                   highlightthickness=0)
        invisible_canvas.pack(side=tk.LEFT, padx=5)
        invisible_canvas.create_oval(2, 2, 10, 10, fill=self.colors['invisible'], outline="")
        
        invisible_select_frame = tk.Frame(invisible_frame, bg=self.colors['bg'])
        invisible_select_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        invisible_radio = ttk.Radiobutton(invisible_select_frame, 
                                        text="Invisible",
                                        variable=status_var, 
                                        value="invisible",
                                        style='Discord.TLabel',
                                        command=lambda: status_description.set("You appear as offline but have full functionality"))
        invisible_radio.pack(side=tk.LEFT)
        
        def update_selection_highlight():
            current_status = status_var.get()
            online_select_frame.config(bg=self.colors['accent'] if current_status == "online" else self.colors['bg'])
            offline_select_frame.config(bg=self.colors['accent'] if current_status == "offline" else self.colors['bg'])
            invisible_select_frame.config(bg=self.colors['accent'] if current_status == "invisible" else self.colors['bg'])
            dialog.after(100, update_selection_highlight)
        
        update_selection_highlight()
        
        def update_status():
            new_status = status_var.get()
            # Update peer offline mode when changing to/from offline status
            self.chat_client.peer.set_offline_mode(new_status == "offline")
            
            success = self._set_user_status(new_status)
            if success:
                self.user_status = new_status
                # Update sync status message
                if new_status == "offline":
                    self._update_sync_status("Working offline - messages will sync when online")
                elif self.user_status == "offline":  # Was offline before
                    self._update_sync_status("Syncing offline content...")
                dialog.destroy()
                # Refresh main frame to update status display
                self.show_main_frame()
            else:
                messagebox.showerror("Error", f"Failed to change status to {new_status}")
        
        # Apply button
        apply_btn = tk.Button(dialog,
                            text="Apply",
                            command=update_status,
                            bg=self.colors['accent'],
                            fg=self.colors['text'],
                            font=('Helvetica', 12),  # Made font size consistent
                            relief=tk.FLAT)
        apply_btn.pack(pady=10)

    def _get_user_status(self):
        """Get the current user status from server"""
        if self.chat_client.is_visitor:
            return "online"  # Visitors are always online
            
        # Get user status from database through the server
        # For a real implementation, you would query the server for this info
        # For now, we'll use a direct query from the chat_client
        if hasattr(self.chat_client, 'username') and self.chat_client.username:
            # For simplicity, just return the current value
            # In a real implementation, query the server for the current status
            return self.user_status
        
        return "online"  # Default to online

    def _set_user_status(self, status):
        """Set user status on the server"""
        if self.chat_client.is_visitor:
            return False
            
        # Send request to update status
        request = {
            "type": "STATUS",
            "token": self.chat_client.token,
            "status": status
        }
        
        # Send the request directly to the server
        response = self.chat_client._send_to_central_server(request)
        
        # Debug information to help diagnose issues
        if not response.get("success", False):
            print(f"Status change error: {response.get('message', 'Unknown error')}")
            
        return response.get("success", False)

    def _refresh_online_users(self):
        """Fetch and display the list of online users"""
        # Clear the current list
        for widget in self.online_users_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Get the online users from the server
        online_users = self.chat_client.get_online_users()
        
        if not online_users:
            # If no online users or error, display a message
            no_users_label = ttk.Label(self.online_users_scrollable_frame,
                                    text="No users online",
                                    style='Discord.TLabel',
                                    font=('Helvetica', 10, 'italic'))
            no_users_label.pack(pady=5)
            return
        
        # Add each online user to the list
        for user_data in online_users:
            username = user_data.get("username")
            status = user_data.get("status", "online")
            
            # Skip displaying yourself
            if username == self.chat_client.username:
                continue
                
            # Create a frame for each user
            user_frame = ttk.Frame(self.online_users_scrollable_frame, style='Channel.TFrame')
            user_frame.pack(fill=tk.X, pady=2)
            
            # Status indicator (only if they're visible)
            status_canvas = tk.Canvas(user_frame, width=8, height=8, 
                                   background=self.colors['light_bg'],
                                   highlightthickness=0)
            status_canvas.pack(side=tk.LEFT, padx=5)
            
            # Show different colors based on status
            if status == "online":
                status_color = self.colors['online']
            elif status == "offline":
                status_color = "#747F8D"  # Gray for offline
            else:
                status_color = self.colors['invisible']
                
            status_canvas.create_oval(1, 1, 7, 7, fill=status_color, outline="")
            
            # Username
            user_label = ttk.Label(user_frame,
                                text=username,
                                style='Discord.TLabel',
                                font=('Helvetica', 10))
            user_label.pack(side=tk.LEFT, padx=5)

    def _update_online_users(self):
        """Background thread to periodically update the online users list"""
        while self.running:
            try:
                # Refresh the online users list every 30 seconds
                time.sleep(30)
                # Use after to schedule the refresh on the main thread
                self.root.after(0, self._refresh_online_users)
            except Exception as e:
                print(f"Error updating online users: {e}")

    def _toggle_connection(self):
        """Toggle between online and offline mode"""
        if self.chat_client.peer.is_offline:
            # Going online
            self.chat_client.peer.set_offline_mode(False)
            # Set status back to online
            if self._set_user_status("online"):
                self.user_status = "online"
            self.connection_label.config(text="🟢 Online")
            self.toggle_connection_btn.config(text="Go Offline")
            self._update_sync_status("Syncing offline content...")
            # Refresh the display to show updated status
            self._refresh_online_users()
        else:
            # Going offline
            self.chat_client.peer.set_offline_mode(True)
            # Set status to offline
            if self._set_user_status("offline"):
                self.user_status = "offline"
            self.connection_label.config(text="🔴 Offline")
            self.toggle_connection_btn.config(text="Go Online")
            self._update_sync_status("Working offline - content will sync when online")
            # Refresh the display to show updated status
            self._refresh_online_users()

    def _update_sync_status(self, message):
        """Update the sync status label"""
        self.sync_label.config(text=message)
        
    '''
    async def _start_stream(self):
        """Start streaming video/audio"""
        if self.is_streaming:
            return
            
        config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        ])
        
        try:
            self.local_video = MediaPlayer('/dev/video0', format='v4l2', options={
                'video_size': '640x360'
            })
            
            self.pc = RTCPeerConnection(configuration=config)
            self.pc.addTrack(self.local_video.video)
            
            self.is_streaming = True
            self.stream_button.config(text="Stop Stream")
            
            await self._notify_stream_start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start stream: {str(e)}")
            self._stop_stream()

    def _stop_stream(self):
        """Stop the current stream"""
        if not self.is_streaming:
            return
            
        try:
            if self.pc:
                self.pc.close()
                self.pc = None
                
            if self.local_video:
                self.local_video.stop()
                self.local_video = None
                
            self.is_streaming = False
            if self.stream_button:
                self.stream_button.config(text="Start Stream")
                
            for pc in self.viewers.values():
                pc.close()
            self.viewers.clear()
            self.viewer_count.set("0 viewers")
            
            if self.stream_canvas:
                self.stream_canvas.delete("all")
                
            self._notify_stream_end()
                
        except Exception as e:
            print(f"Error stopping stream: {e}")

    def _toggle_stream(self):
        """Toggle streaming state"""
        if self.is_streaming:
            self._stop_stream()
        else:
            asyncio.run(self._start_stream())

    def _notify_stream_start(self):
        """Notify server that we're starting a stream"""
        return self.chat_client.start_stream(self.current_channel)

    def _notify_stream_end(self):
        """Notify server that we're ending the stream"""
        return self.chat_client.stop_stream(self.current_channel)
        
    async def _handle_viewer_connection(self, username):
        """Handle a new viewer connecting to the stream"""
        if not self.is_streaming:
            return None
            
        config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        ])
        
        pc = RTCPeerConnection(configuration=config)
        
        if self.local_video and self.local_video.video:
            pc.addTrack(self.local_video.video)
        
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        self.viewers[username] = pc
        self.viewer_count.set(f"{len(self.viewers)} viewers")
        
        return pc.localDescription

    def _show_stream_window(self):
        """Show streaming window"""
        if self.stream_window:
            self.stream_window.deiconify()
            return
            
        self.stream_window = tk.Toplevel(self.root)
        self.stream_window.title("Livestream")
        self.stream_window.geometry("800x600")
        self.stream_window.configure(bg=self.colors['bg'])
        
        self.stream_canvas = tk.Canvas(
            self.stream_window,
            bg='black',
            width=640,
            height=360
        )
        self.stream_canvas.pack(pady=20)
        
        controls_frame = ttk.Frame(self.stream_window, style='Main.TFrame')
        controls_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.stream_button = tk.Button(
            controls_frame,
            text="Start Stream",
            command=self._toggle_stream,
            bg=self.colors['accent'],
            fg=self.colors['text'],
            font=('Helvetica', 10),
            relief=tk.FLAT
        )
        
        self.stream_button.pack(side=tk.LEFT, padx=5)
        
        self.viewer_count = tk.StringVar(value="0 viewers")
        viewer_label = ttk.Label(
            controls_frame,
            textvariable=self.viewer_count,
            style='Discord.TLabel'
        )
        viewer_label.pack(side=tk.RIGHT, padx=5)
        
        self.stream_window.protocol("WM_DELETE_WINDOW", self._handle_stream_window_close)

    def _handle_stream_window_close(self):
        """Handle stream window close event"""
        if self.is_streaming:
            self._stop_stream()
        self.stream_window.withdraw()

    def _update_stream_frame(self, frame):
        """Update the stream canvas with a new video frame"""
        try:
            if frame is not None and self.stream_canvas:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = frame_rgb.shape[:2]
                photo = tk.PhotoImage(data=cv2.imencode('.ppm', frame_rgb)[1].tobytes())
                self.stream_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.stream_canvas.image = photo
        except Exception as e:
            print(f"Error updating stream frame: {e}")
    '''
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    gui = ChatGUI()
    gui.run()
