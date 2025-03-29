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
import websockets
from stream_handler import StreamHandler  # Add this import
from PIL import Image, ImageTk

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
        # Initialize asyncio loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create the main window
        self.root = tk.Tk()
        self.root.title("Discord but without rd")
        self.root.geometry("1200x800")
        
        # Set up asyncio integration with Tkinter
        def run_asyncio_tasks():
            while True:
                try:
                    self.loop.run_until_complete(asyncio.sleep(0.1))
                    self.root.after(10, run_asyncio_tasks)
                    break
                except Exception as e:
                    print(f"Error in asyncio loop: {e}")
        
        # Start the asyncio task handler
        self.root.after(0, run_asyncio_tasks)
        
        # Set color scheme first
        self.colors = {
            'bg': '#36393F',  # Discord dark background
            'light_bg': '#40444B',  # Discord lighter background
            'dark_bg': '#2F3136',  # Discord darker background
            'accent': '#7289DA',  # Discord blurple
            'text': '#FFFFFF',  # White text
            'secondary_text': '#B9BBBE',  # Discord secondary text
            'input_bg': '#40444B',  # Discord input background
            'online': '#43B581',    # Discord online status color
            'invisible': '#747F8D',  # Discord invisible status color
            'error': '#F04747'      # Discord error color
        }
        
        # Initialize chat client with auto-detected server IP
        self.chat_client = ChatClient(get_local_ip(), 8000)
        
        # Initialize stream handler with chat client reference
        self.stream_handler = StreamHandler()
        self.stream_handler.chat_client = self.chat_client
        self.stream_active = False
        
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
        
        # Channel label
        self.channel_label = ttk.Label(right_frame,
                                     text="Select a channel",
                                     style='Discord.TLabel',
                                     font=('Helvetica', 14, 'bold'))
        self.channel_label.pack(pady=10)
        
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
        
        # Stream button (only for channel owners)
        if not self.chat_client.is_visitor:
            self.stream_btn = tk.Button(message_frame,
                                      text="🎥 Start Stream",
                                      command=self._show_stream_window,
                                      bg=self.colors['accent'],
            fg=self.colors['text'],
                                      font=('Helvetica', 10),
            relief=tk.FLAT)
            self.stream_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Watch Stream button
        self.watch_stream_btn = tk.Button(message_frame,
                                        text="👁️ Watch Stream",
                                        command=lambda: self.loop.create_task(self._check_and_join_stream()),
                                        bg=self.colors['accent'],
                                        fg=self.colors['text'],
                                        font=('Helvetica', 10),
                                        relief=tk.FLAT)
        self.watch_stream_btn.pack(side=tk.LEFT, padx=(0, 5))
        
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
        """Join the selected channel"""
        selection = self.channel_listbox.curselection()
        if not selection:
            return

        # Extract channel name from the selection (remove the owner part)
        channel_text = self.channel_listbox.get(selection[0])
        channel_name = channel_text.split(" (")[0]  # Get just the channel name before the owner part

        # Join channel
        if self.chat_client.join_channel(channel_name):
            # Get message history
            messages = self.chat_client.get_channel_history(channel_name)
            
            # Clear existing messages
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete('1.0', tk.END)
            
            # Display messages
            if messages:
                for msg in messages:
                    timestamp = msg["timestamp"].split("T")[1].split(".")[0]  # Extract time
                    message_text = f"[{timestamp}] {msg['username']}: {msg['content']}\n"
                    self.chat_display.insert(tk.END, message_text)
                self.chat_display.see(tk.END)  # Scroll to bottom
            
            self.chat_display.config(state=tk.DISABLED)
            
            # Update channel label
            self.channel_label.config(text=f"Channel: {channel_name}")
            
            # Set current channel
            self.current_channel = channel_name
            
            # Check for active stream
            stream_info = self.chat_client.get_stream_info(channel_name)
            if stream_info:
                if messagebox.askyesno("Active Stream", 
                    f"There is an active stream in this channel by {stream_info['streamer']}.\nWould you like to join?"):
                    # Use create_task to handle the async call
                    self.loop.create_task(self._show_viewer_window(channel_name, stream_info))
        else:
            messagebox.showerror("Error", f"Failed to join channel: {channel_name}")
    
    async def _show_viewer_window(self, channel_name, stream_info):
        """Show the viewer window for watching a stream"""
        # Create viewer window
        viewer_window = tk.Toplevel(self.root)
        viewer_window.title(f"Stream Viewer - {channel_name}")
        viewer_window.geometry("1200x700")  # Increased width to accommodate chat
        
        # Configure window style
        viewer_window.configure(bg=self.colors['light_bg'])
        
        # Create main frame
        main_frame = ttk.Frame(viewer_window, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create left frame for video
        video_frame = ttk.Frame(main_frame, style='Main.TFrame')
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Video display with specific size
        video_display = tk.Label(video_frame,
                               text="Initializing camera...",
                               bg="black",  # Set to black for better visibility
                               fg="white",
                               font=('Helvetica', 14))
        video_display.pack(fill=tk.BOTH, expand=True)

        # Configure video frame with fixed size
        video_frame.configure(width=640, height=480)
        video_frame.pack_propagate(False)  # Prevent frame from shrinking

        # Create right frame for chat
        chat_frame = ttk.Frame(main_frame, style='Main.TFrame')
        chat_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        
        # Configure chat frame with fixed width
        chat_frame.configure(width=400)
        chat_frame.pack_propagate(False)  # Prevent frame from shrinking
        
        # Chat header
        chat_header = ttk.Label(chat_frame,
                              text="Stream Chat",
                              style='Discord.TLabel',
                              font=('Helvetica', 14, 'bold'))
        chat_header.pack(pady=(0, 5))
        
        # Chat display
        chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg=self.colors['light_bg'],
            fg=self.colors['text'],
            font=('Helvetica', 10),
            state=tk.DISABLED,
            height=20
        )
        chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Chat input frame
        chat_input_frame = ttk.Frame(chat_frame, style='Main.TFrame')
        chat_input_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Chat input field
        chat_entry = ttk.Entry(chat_input_frame, style='Discord.TEntry')
        chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Send button
        send_btn = tk.Button(chat_input_frame,
                           text="Send",
                           command=lambda: self.loop.create_task(send_stream_message()),
                           bg=self.colors['accent'],
                           fg=self.colors['text'],
                           font=('Helvetica', 10),
                           relief=tk.FLAT)
        send_btn.pack(side=tk.RIGHT)

        # WebRTC connection variables
        pc = None
        video_track = None
        running = True

        # Controls frame
        controls_frame = ttk.Frame(video_frame, style='Main.TFrame')
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Status label
        status_label = ttk.Label(controls_frame,
                               text="Connecting...",
                               style='Discord.TLabel')
        status_label.pack(side=tk.LEFT, padx=5)
        
        # Close button
        close_btn = tk.Button(controls_frame,
                            text="Close",
                            command=lambda: self.loop.create_task(handle_close()),
                            bg=self.colors['light_bg'],
                            fg=self.colors['text'],
                            font=('Helvetica', 12),
                            relief=tk.FLAT)
        close_btn.pack(side=tk.RIGHT, padx=5)

        async def send_stream_message():
            """Send a chat message in the stream"""
            message = chat_entry.get().strip()
            if not message:
                return
                
            # Clear input field
            chat_entry.delete(0, tk.END)
            
            # Create message data
            msg_data = {
                "type": "STREAM_MESSAGE",
                "token": self.chat_client.token,
                "channel": channel_name,
                "content": message,
                "username": self.chat_client.username,
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to central server
            response = self.chat_client._send_to_central_server(msg_data)
            
            if response.get("success"):
                # Message will be displayed when received through the update mechanism
                pass
            else:
                # Show error in chat
                display_chat_message("System", "Failed to send message", error=True)

        def display_chat_message(username, content, error=False):
            """Display a chat message in the chat display"""
            chat_display.config(state=tk.NORMAL)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if error:
                # Show error messages in red
                chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
                chat_display.insert(tk.END, f"{content}\n", "error")
            else:
                chat_display.insert(tk.END, f"[{timestamp}] {username}: {content}\n")
            
            chat_display.see(tk.END)
            chat_display.config(state=tk.DISABLED)
        
        # Configure chat display tags
        chat_display.tag_configure("error", foreground="red")
        chat_display.tag_configure("timestamp", foreground=self.colors['secondary_text'])
        
        # Bind Enter key to send message
        chat_entry.bind('<Return>', lambda e: self.loop.create_task(send_stream_message()))
        
        # Start message update loop
        async def update_stream_messages():
            """Periodically check for new stream messages"""
            last_message_id = 0
            while running:
                try:
                    # Get new messages from server
                    request = {
                        "type": "GET_STREAM_MESSAGES",
                        "token": self.chat_client.token,
                        "channel": channel_name,
                        "since_id": last_message_id
                    }
                    
                    response = self.chat_client._send_to_central_server(request)
                    if response.get("success"):
                        messages = response.get("messages", [])
                        for msg in messages:
                            display_chat_message(msg["username"], msg["content"])
                            last_message_id = max(last_message_id, msg.get("id", 0))
                    
                    await asyncio.sleep(1)  # Check every second
                    
                except Exception as e:
                    print(f"Error updating stream messages: {e}")
                    await asyncio.sleep(1)

        async def display_video():
            """Display video frames from the track"""
            nonlocal video_track, running
            frame_count = 0
            last_frame_time = time.time()
            consecutive_errors = 0
            last_frame = None  # Keep last frame as backup
            
            print(f"Starting display loop with track: kind={video_track.kind}, id={video_track.id}")
            print(f"Track readyState: {video_track.readyState}")
            
            try:
                while running and video_track:
                    try:
                        # First try with short timeout
                        try:
                            frame = await asyncio.wait_for(video_track.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            print(f"Short timeout waiting for frame, track state: {video_track.readyState}")
                            # Try again with longer timeout
                            try:
                                frame = await asyncio.wait_for(video_track.recv(), timeout=5.0)
                            except asyncio.TimeoutError:
                                print(f"Long timeout waiting for frame, track state: {video_track.readyState}")
                                if consecutive_errors > 5:
                                    print("Too many consecutive timeouts, resetting connection")
                                    break
                                consecutive_errors += 1
                                continue
                        
                        if frame is None or frame.width == 0 or frame.height == 0:
                            print("Received empty frame")
                            if last_frame is not None:
                                frame = last_frame
                            else:
                                continue
                        
                        # Convert frame to array
                        frame_time = time.time()
                        frame_delay = frame_time - last_frame_time
                        print(f"Frame #{frame_count} received after {frame_delay:.3f}s, PTS={frame.pts}, time_base={frame.time_base}")
                        
                        # Get frame data
                        frame_data = frame.to_ndarray(format="rgb24")
                        if frame_data is None or frame_data.size == 0:
                            print("Failed to convert frame to array")
                            continue
                            
                        print(f"Frame shape: {frame_data.shape}, dtype: {frame_data.dtype}")
                        
                        # Convert to PIL Image
                        image = Image.fromarray(frame_data)
                        print(f"PIL Image size: {image.size}, mode: {image.mode}")
                        
                        # Resize if needed
                        if image.size != (640, 480):
                            image = image.resize((640, 480), Image.LANCZOS)
                        
                        try:
                            # Convert to PhotoImage
                            photo = ImageTk.PhotoImage(image=image)
                            
                            # Update display
                            video_display.configure(image=photo)
                            video_display.image = photo  # Keep reference
                            
                            frame_count += 1
                            last_frame_time = frame_time
                            last_frame = frame  # Store successful frame
                            consecutive_errors = 0  # Reset error count
                            
                        except Exception as e:
                            print(f"Error creating PhotoImage: {e}")
                            consecutive_errors += 1
                            
                        # Control frame rate
                        await asyncio.sleep(1/30)  # 30 FPS
                        
                    except Exception as e:
                        print(f"Error in display loop: {e}")
                        consecutive_errors += 1
                        if consecutive_errors > 5:
                            print("Too many consecutive errors, resetting connection")
                            break
                            
            except Exception as e:
                print(f"Fatal error in display loop: {e}")
            finally:
                print("Display loop ended")
                if running:
                    status_label.config(text="Stream ended")

        async def handle_close():
            """Handle window close"""
            nonlocal running
            running = False
            
            if video_track:
                video_track.stop()
            
            if pc:
                await pc.close()
                
            viewer_window.destroy()

        async def connect_to_stream():
            nonlocal pc, video_track, running
            
            try:
                # Get streamer's IP address from stream info
                streamer_ip = stream_info.get('streamer_ip')
                if not streamer_ip:
                    raise Exception("Streamer IP address not available")
                    
                print(f"Connecting to streamer at {streamer_ip}:8765")
                
                # Create peer connection with STUN server
                pc = RTCPeerConnection(configuration=RTCConfiguration([
                    RTCIceServer(urls=["stun:stun.l.google.com:19302"])
                ]))
                
                # Set up track handler before connecting
                @pc.on("track")
                def on_track(track):
                    nonlocal video_track
                    if track.kind == "video":
                        print(f"Received video track: kind={track.kind}, id={track.id}")  # Debug log
                        video_track = track
                        status_label.config(text="Stream connected")
                        print("Starting display loop...")  # Debug log
                        # Start video display loop using the existing event loop
                        self.loop.create_task(display_video())
                
                # Add connection state change handler
                @pc.on("connectionstatechange")
                async def on_connectionstatechange():
                    state = pc.connectionState
                    print(f"Connection state changed to: {state}")
                    status_label.config(text=f"Connection: {state}")
                    
                    if state == "connected":
                        print("Connection established, waiting for video track...")
                    elif state == "failed":
                        print("Connection failed, closing...")
                        await handle_close()
                
                # Add ICE connection state change handler
                @pc.on("iceconnectionstatechange")
                async def on_iceconnectionstatechange():
                    print(f"ICE connection state: {pc.iceConnectionState}")
                    if pc.iceConnectionState == "failed":
                        print("ICE connection failed")
                        await handle_close()
                
                # Connection retry logic with increasing delays
                max_retries = 3
                retry_count = 0
                retry_delays = [1, 2, 4]  # Exponential backoff
                
                while retry_count < max_retries and running:
                    try:
                        # Create WebSocket connection for signaling
                        async with websockets.connect(
                            f'ws://{streamer_ip}:8765',
                            ping_interval=None,  # Disable ping to prevent timeouts
                            ping_timeout=None,
                            close_timeout=10  # Add close timeout
                        ) as websocket:
                            print("WebSocket connection established")
                            status_label.config(text="Connected to streamer")
                            
                            # Send join message
                            join_message = {
                                "type": "join",
                                "viewer_id": self.chat_client.username
                            }
                            print(f"Sending join message: {join_message}")
                            await websocket.send(json.dumps(join_message))
                            
                            # Wait for offer with timeout
                            try:
                                print("Waiting for offer...")
                                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                                data = json.loads(response)
                                print(f"Received response: {data}")
                                
                                if data["type"] == "offer":
                                    print("Processing offer...")
                                    # Set remote description
                                    await pc.setRemoteDescription(RTCSessionDescription(
                                        sdp=data["offer"]["sdp"],
                                        type=data["offer"]["type"]
                                    ))
                                    
                                    # Create and set local description
                                    answer = await pc.createAnswer()
                                    await pc.setLocalDescription(answer)
                                    
                                    print("Sending answer...")
                                    await websocket.send(json.dumps({
                                        "type": "answer",
                                        "viewer_id": self.chat_client.username,
                                        "answer": {
                                            "sdp": pc.localDescription.sdp,
                                            "type": pc.localDescription.type
                                        }
                                    }))
                                    
                                    # Handle ICE candidates
                                    @pc.on("icecandidate")
                                    async def on_ice_candidate(event):
                                        if event.candidate and running:
                                            print(f"Sending ICE candidate: {event.candidate}")
                                            await websocket.send(json.dumps({
                                                "type": "ice_candidate",
                                                "viewer_id": self.chat_client.username,
                                                "candidate": {
                                                    "candidate": event.candidate.candidate,
                                                    "sdpMid": event.candidate.sdpMid,
                                                    "sdpMLineIndex": event.candidate.sdpMLineIndex
                                                }
                                            }))
                                    
                                    # Keep connection alive and handle incoming messages
                                    while running:
                                        try:
                                            print("Waiting for ICE candidates...")
                                            message = await websocket.recv()
                                            data = json.loads(message)
                                            
                                            if data["type"] == "ice_candidate" and data.get("candidate"):
                                                print("Processing ICE candidate...")
                                                candidate = data["candidate"]
                                                await pc.addIceCandidate(RTCIceCandidate(
                                                    sdpMid=candidate["sdpMid"],
                                                    sdpMLineIndex=candidate["sdpMLineIndex"],
                                                    candidate=candidate["candidate"]
                                                ))
                                                print("ICE candidate added successfully")
                                                
                                        except websockets.exceptions.ConnectionClosed:
                                            print("WebSocket connection closed")
                                            break
                                            
                                        except Exception as e:
                                            print(f"Error handling message: {e}")
                                            if not websocket.open or not running:
                                                break
                                            
                            except asyncio.TimeoutError:
                                print("Timeout waiting for offer")
                                raise Exception("Timeout waiting for offer")
                                
                    except websockets.exceptions.WebSocketException as e:
                        retry_count += 1
                        if retry_count < max_retries and running:
                            delay = retry_delays[retry_count - 1]
                            print(f"Connection refused, retrying in {delay}s ({retry_count}/{max_retries})...")
                            status_label.config(text=f"Connection failed, retrying {retry_count}/{max_retries}...")
                            await asyncio.sleep(delay)
                        else:
                            raise Exception("Failed to connect to streamer after multiple attempts")
                            
            except Exception as e:
                print(f"Error connecting to stream: {e}")
                status_label.config(text="Connection failed")
                messagebox.showerror("Error", f"Failed to connect to stream: {str(e)}")
                await handle_close()
        
        # Start message update loop
        self.loop.create_task(update_stream_messages())
        
        # Handle window close event
        viewer_window.protocol("WM_DELETE_WINDOW", lambda: self.loop.create_task(handle_close()))
        
        # Start connection using the existing event loop
        self.loop.create_task(connect_to_stream())

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
        
    def _show_stream_window(self):
        """Show the stream window with video display"""
        if not self.current_channel:
            messagebox.showwarning("Warning", "Please join a channel first")
            return
            
        # Check if user is channel owner
        channels = self.chat_client._list_channels()
        if self.current_channel not in channels or channels[self.current_channel]['owner'] != self.chat_client.username:
            messagebox.showwarning("Warning", "Only channel owner can start streaming")
            return
            
        # Create stream window
        self.stream_window = tk.Toplevel(self.root)
        self.stream_window.title(f"Stream - {self.current_channel}")
        self.stream_window.geometry("1200x700")  # Increased width to accommodate chat
        self.stream_window.configure(bg=self.colors['dark_bg'])
        
        # Create main frame
        main_frame = ttk.Frame(self.stream_window, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create left frame for video
        video_frame = ttk.Frame(main_frame, style='Main.TFrame')
        video_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Create video display label
        self.video_label = tk.Label(
            video_frame,
            text="Initializing camera...",
            font=("Arial", 14),
            fg="white",
            bg="black"
        )
        self.video_label.pack(fill=tk.BOTH, expand=True)
        
        # Configure video frame with fixed size
        video_frame.configure(width=640, height=480)
        video_frame.pack_propagate(False)
        
        # Create controls frame
        controls_frame = ttk.Frame(video_frame, style='Main.TFrame')
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Initialize viewer count
        self.viewer_count = 0
        
        # Create viewer count label
        self.viewer_count_label = tk.Label(
            controls_frame,
            text="Viewers: 0",
            font=("Arial", 12),
            fg="white",
            bg=self.colors['dark_bg']
        )
        self.viewer_count_label.pack(side=tk.LEFT, pady=5)
        
        # Create stream control button
        self.stream_button = tk.Button(
            controls_frame,
            text="Start Stream",
            font=("Arial", 12),
            command=self._toggle_stream
        )
        self.stream_button.pack(side=tk.RIGHT, pady=5)

        # Create right frame for chat
        chat_frame = ttk.Frame(main_frame, style='Main.TFrame')
        chat_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        
        # Configure chat frame with fixed width
        chat_frame.configure(width=400)
        chat_frame.pack_propagate(False)
        
        # Chat header
        chat_header = ttk.Label(chat_frame,
                              text="Stream Chat",
                              style='Discord.TLabel',
                              font=('Helvetica', 14, 'bold'))
        chat_header.pack(pady=(0, 5))
        
        # Chat display
        self.stream_chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg=self.colors['light_bg'],
            fg=self.colors['text'],
            font=('Helvetica', 10),
            state=tk.DISABLED,
            height=20
        )
        self.stream_chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Configure chat display tags
        self.stream_chat_display.tag_configure("error", foreground="red")
        self.stream_chat_display.tag_configure("timestamp", foreground=self.colors['secondary_text'])
        
        # Chat input frame
        chat_input_frame = ttk.Frame(chat_frame, style='Main.TFrame')
        chat_input_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Chat input field
        self.stream_chat_entry = ttk.Entry(chat_input_frame, style='Discord.TEntry')
        self.stream_chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Send button
        send_btn = tk.Button(chat_input_frame,
                           text="Send",
                           command=lambda: self.loop.create_task(self._send_stream_message()),
                           bg=self.colors['accent'],
                           fg=self.colors['text'],
                           font=('Helvetica', 10),
                           relief=tk.FLAT)
        send_btn.pack(side=tk.RIGHT)
        
        # Bind Enter key to send message
        self.stream_chat_entry.bind('<Return>', lambda e: self.loop.create_task(self._send_stream_message()))
        
        # Start message update loop when streaming starts
        self.stream_messages_task = None
            
        # Set up closing protocol
        def on_closing():
            if self.stream_active:
                if messagebox.askyesno("Confirm", "Stop stream and close window?"):
                    self.loop.create_task(self._stop_stream())
                    self.stream_window.destroy()
            else:
                self.stream_window.destroy()
                
        self.stream_window.protocol("WM_DELETE_WINDOW", on_closing)

    async def _send_stream_message(self):
        """Send a chat message in the stream"""
        if not self.stream_active:
            return
            
        message = self.stream_chat_entry.get().strip()
        if not message:
            return
            
        # Clear input field
        self.stream_chat_entry.delete(0, tk.END)
        
        # Create message data
        msg_data = {
            "type": "STREAM_MESSAGE",
            "token": self.chat_client.token,
            "channel": self.current_channel,
            "content": message,
            "username": self.chat_client.username,
            "timestamp": datetime.now().isoformat()
        }
        
        # Send to central server
        response = self.chat_client._send_to_central_server(msg_data)
        
        if response.get("success"):
            # Message will be displayed through the update mechanism
            pass
        else:
            # Show error in chat
            self._display_stream_chat_message("System", "Failed to send message", error=True)

    def _display_stream_chat_message(self, username, content, error=False):
        """Display a chat message in the stream chat display"""
        if not hasattr(self, 'stream_chat_display'):
            return
            
        self.stream_chat_display.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if error:
            # Show error messages in red
            self.stream_chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
            self.stream_chat_display.insert(tk.END, f"{content}\n", "error")
        else:
            self.stream_chat_display.insert(tk.END, f"[{timestamp}] {username}: {content}\n")
        
        self.stream_chat_display.see(tk.END)
        self.stream_chat_display.config(state=tk.DISABLED)

    async def _update_stream_messages(self):
        """Periodically check for new stream messages"""
        last_message_id = 0
        while self.stream_active:
            try:
                # Get new messages from server
                request = {
                    "type": "GET_STREAM_MESSAGES",
                    "token": self.chat_client.token,
                    "channel": self.current_channel,
                    "since_id": last_message_id
                }
                
                response = self.chat_client._send_to_central_server(request)
                if response.get("success"):
                    messages = response.get("messages", [])
                    for msg in messages:
                        self._display_stream_chat_message(msg["username"], msg["content"])
                        last_message_id = max(last_message_id, msg.get("id", 0))
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                print(f"Error updating stream messages: {e}")
                await asyncio.sleep(1)

    def _toggle_stream(self):
        """Toggle stream start/stop"""
        if not self.stream_active:
            self.loop.create_task(self._start_stream())
        else:
            self.loop.create_task(self._stop_stream())

    async def _start_stream(self):
        """Start streaming in the current channel"""
        if not self.current_channel:
            messagebox.showwarning("Warning", "Please join a channel first")
            return False
            
        if self.chat_client.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot start streaming")
            return False
            
        try:
            # Set channel and streamer info
            self.stream_handler.set_channel(self.current_channel)
            self.stream_handler.set_streamer(self.chat_client.username, self.chat_client.token)
            
            # Set viewer count callback
            self.stream_handler.set_viewer_callback(self.update_viewer_count)
            
            # Start the stream first
            success = await self.stream_handler.start_stream()
            if success:
                # Now set the display window after the video track is created
                if self.stream_handler.video_track:
                    self.stream_handler.video_track.set_display_window(self.video_label)
                    # Start displaying frames
                    self.loop.create_task(self._update_video_display())
                    
                self.stream_active = True
                # Update UI to show stream is active
                self.stream_button.config(text="Stop Stream")
                self.update_viewer_count(0)  # Initialize viewer count
                
                # Start message update loop
                self.stream_messages_task = self.loop.create_task(self._update_stream_messages())
                
                return True
            else:
                messagebox.showerror("Error", "Failed to start stream")
                return False
        except Exception as e:
            print(f"Error starting stream: {e}")
            messagebox.showerror("Error", f"Failed to start stream: {str(e)}")
            return False

    async def _update_video_display(self):
        """Update the video display with frames from the camera"""
        try:
            while self.stream_active:
                # Get the next frame from the video track
                frame = await self.stream_handler.video_track.recv()
                
                if frame:
                    # Convert VideoFrame to numpy array
                    frame_array = frame.to_ndarray(format="bgr24")
                    
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame_array, cv2.COLOR_BGR2RGB)
                    
                    # Convert to PIL Image
                    image = Image.fromarray(frame_rgb)
                    
                    # Resize if needed while maintaining aspect ratio
                    display_width = 640  # You can adjust these values
                    display_height = 480
                    image.thumbnail((display_width, display_height), Image.LANCZOS)
                    
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(image=image)
                    
                    # Update label with new image
                    # Keep a reference to avoid garbage collection
                    self.current_photo = photo
                    self.video_label.configure(image=photo)
                    self.video_label.image = photo
                    
                    # Small delay to control frame rate
                    await asyncio.sleep(1/30)  # 30 FPS
                    
        except Exception as e:
            if self.stream_active:  # Only show error if streaming is still active
                print(f"Error updating video display: {str(e)}")
                self.video_label.configure(text=f"Video display error: {str(e)}")

    async def _stop_stream(self):
        """Stop the current stream"""
        try:
            # Cancel message update task if running
            if self.stream_messages_task and not self.stream_messages_task.done():
                self.stream_messages_task.cancel()
                try:
                    await self.stream_messages_task
                except asyncio.CancelledError:
                    pass
            
            await self.stream_handler.stop_stream()
            self.stream_active = False
            # Update UI to show stream is stopped
            self.stream_button.config(text="Start Stream")
            self.update_viewer_count(0)
            
            # Clear chat display but don't delete messages (they're saved on server)
            if hasattr(self, 'stream_chat_display'):
                self.stream_chat_display.config(state=tk.NORMAL)
                self.stream_chat_display.delete('1.0', tk.END)
                self.stream_chat_display.config(state=tk.DISABLED)
                
        except Exception as e:
            print(f"Error stopping stream: {e}")
            messagebox.showerror("Error", f"Failed to stop stream: {str(e)}")

    def update_viewer_count(self, count):
        """Update the viewer count display"""
        if hasattr(self, 'viewer_count_label'):
            self.viewer_count_label.config(text=f"Viewers: {count}")

    async def _check_and_join_stream(self):
        """Check for active stream and join if available"""
        if not self.current_channel:
            messagebox.showwarning("Warning", "Please join a channel first")
            return
            
        # Check for active stream
        stream_info = self.chat_client.get_stream_info(self.current_channel)
        print(f"Stream info received: {stream_info}")  # Debug log
        
        if stream_info:
            # Verify streamer IP is available
            streamer_ip = stream_info.get('streamer_ip')
            if not streamer_ip:
                messagebox.showerror("Error", "Cannot connect to stream: Streamer IP address not available")
                return
                
            print(f"Found active stream from {stream_info.get('streamer')} at {streamer_ip}")
            if messagebox.askyesno("Join Stream", 
                f"There is an active stream in this channel by {stream_info.get('streamer', 'Unknown')}.\nWould you like to join?"):
                await self._show_viewer_window(self.current_channel, stream_info)
        else:
            print("No stream info received")  # Debug log
            messagebox.showinfo("No Stream", "There is no active stream in this channel.")
    
    def run(self):
        try:
            self.root.mainloop()
        finally:
            # Clean up asyncio loop
            self.loop.stop()
            self.loop.close()

if __name__ == "__main__":
    gui = ChatGUI()
    gui.run()
