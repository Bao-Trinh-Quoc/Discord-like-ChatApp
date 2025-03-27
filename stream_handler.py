import cv2
import numpy as np
from PIL import Image, ImageTk
import threading
import asyncio
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration
from av import VideoFrame  # Import VideoFrame from av package
import socket
import logging
from aiortc.contrib.media import MediaPlayer, MediaRecorder
import json
import queue
import time
import tkinter as tk
from aiortc import VideoStreamTrack as BaseVideoStreamTrack

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

class VideoStreamTrack(MediaStreamTrack):
    """Video stream track for WebRTC streaming"""
    kind = "video"
    
    def __init__(self):
        super().__init__()
        self.timestamp = 0  # Initialize timestamp counter
        self._init_camera()
        self._current_image = None  # Store current PhotoImage
        self._display_window = None
        self._running = True
        
    def _init_camera(self):
        """Initialize the camera with proper error handling"""
        print("Initializing camera...")
        self.cap = None
        
        # Try camera indices 0 and 1
        for index in [0, 1]:
            try:
                self.cap = cv2.VideoCapture(index)
                if self.cap.isOpened():
                    print(f"Successfully opened camera at index {index}")
                    
                    # Set camera properties
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    self.cap.set(cv2.CAP_PROP_FPS, 30)
                    
                    # Verify camera properties were set
                    width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                    height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    fps = self.cap.get(cv2.CAP_PROP_FPS)
                    print(f"Camera properties - Width: {width}, Height: {height}, FPS: {fps}")
                    
                    # Test frame capture
                    ret, frame = self.cap.read()
                    if ret:
                        if frame.shape[0] > 0 and frame.shape[1] > 0:
                            print(f"Successfully captured test frame with shape {frame.shape}")
                            # Convert to RGB to test conversion
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            print("Successfully converted frame to RGB")
                            return
                        else:
                            print(f"Invalid frame shape: {frame.shape}")
                            self.cap.release()
                    else:
                        print("Failed to capture test frame")
                        self.cap.release()
                else:
                    print(f"Failed to open camera at index {index}")
                    
            except Exception as e:
                print(f"Error initializing camera at index {index}: {e}")
                if self.cap:
                    self.cap.release()
                    
        raise Exception("Failed to initialize camera - no working camera found")
        
    def stop(self):
        """Stop the video track"""
        self._running = False
        if self.cap:
            self.cap.release()
        super().stop()
        
    def set_display_window(self, window):
        """Set the window for displaying video frames"""
        self._display_window = window
        
    async def recv(self):
        """Get the next video frame"""
        if not self._running:
            raise Exception("Track has ended")
            
        try:
            # Capture frame
            ret, frame = self.cap.read()
            if not ret:
                raise Exception("Failed to capture frame")
                
            # Convert frame to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Update display if window is set
            if self._display_window:
                try:
                    # Convert to PIL Image
                    image = Image.fromarray(frame)
                    
                    # Resize if needed
                    if image.size != (640, 480):
                        image = image.resize((640, 480), Image.NEAREST)
                        
                    # Convert to PhotoImage
                    photo = ImageTk.PhotoImage(image=image)
                    
                    # Store reference to prevent garbage collection
                    self._current_image = photo
                    
                    # Update display
                    self._display_window.configure(image=photo)
                    self._display_window.image = photo  # Keep reference
                    
                    print("Frame displayed successfully")
                    
                except Exception as e:
                    print(f"Error updating display: {e}")
                    
            # Convert frame to video frame
            video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
            video_frame.pts = self.timestamp
            self.timestamp += 1
            return video_frame
            
        except Exception as e:
            print(f"Error in recv: {e}")
            raise Exception(f"Frame capture error: {str(e)}")

class StreamHandler:
    """Handles WebRTC streaming functionality"""
    
    def __init__(self):
        self.pc = None
        self.video_track = None
        self.viewers = {}  # Dictionary of peer connections for viewers
        self.is_streaming = False
        self.channel = None  # Store the channel name
        self.streamer = None  # Store streamer username
        self.token = None  # Store authentication token
        self.signaling_server = None  # Store signaling server reference
        self.chat_client = None  # Reference to chat client
        
        # WebRTC configuration
        self.config = RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"])
        ])
        
    def set_channel(self, channel):
        """Set the channel name for this stream"""
        self.channel = channel
        
    def set_streamer(self, username, token):
        """Set streamer information"""
        self.streamer = username
        self.token = token
        
    async def start_stream(self):
        """Start the stream"""
        try:
            print("Initializing video track...")
            # Create video track first
            try:
                self.video_track = VideoStreamTrack()
                print("Video track created successfully")
            except Exception as e:
                print(f"Failed to create video track: {e}")
                raise Exception(f"Failed to initialize camera: {str(e)}")
            
            print("Creating peer connection...")
            # Create peer connection
            self.pc = RTCPeerConnection(configuration=self.config)
            
            print("Adding video track to peer connection...")
            # Add video track
            self.pc.addTrack(self.video_track)
            
            print("Creating offer...")
            # Create offer
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            
            self.is_streaming = True
            print(f"Stream started successfully in channel: {self.channel}")
            
            # Notify central server about active stream
            if self.channel and self.streamer and self.token and self.chat_client:
                request = {
                    "type": "STREAM_START",
                    "token": self.token,
                    "channel": self.channel
                }
                response = self.chat_client._send_to_central_server(request)
                if not response.get("success"):
                    print(f"Failed to notify server about stream: {response.get('message')}")
                    return False
                print("Stream registered with central server")
            else:
                print("Missing required information to register stream")
                return False
            
            return True
            
        except Exception as e:
            print(f"Error starting stream: {e}")
            await self.stop_stream()
            return False
            
    async def stop_stream(self):
        """Stop the stream"""
        print("Stopping stream...")
        if self.video_track:
            self.video_track.stop()
        
        # Close all viewer connections
        for viewer_id, viewer_pc in self.viewers.items():
            await viewer_pc.close()
        self.viewers.clear()
        
        # Close main peer connection
        if self.pc:
            await self.pc.close()
        
        # Close signaling server
        if self.signaling_server:
            self.signaling_server.close()
            await self.signaling_server.wait_closed()
        
        self.is_streaming = False
        
        # Notify central server that stream has ended
        if self.channel and self.token and self.chat_client:
            request = {
                "type": "STREAM_END",
                "token": self.token,
                "channel": self.channel
            }
            self.chat_client._send_to_central_server(request)
        
        print("Stream stopped successfully")
            
    async def handle_viewer_connection(self, viewer_id):
        """Handle a new viewer connection"""
        if not self.is_streaming:
            return None
            
        try:
            print(f"Handling viewer connection for {viewer_id}")
            # Create peer connection for viewer
            viewer_pc = RTCPeerConnection(configuration=self.config)
            
            # Add video track
            viewer_pc.addTrack(self.video_track)
            
            # Create offer
            offer = await viewer_pc.createOffer()
            await viewer_pc.setLocalDescription(offer)
            
            # Store viewer connection
            self.viewers[viewer_id] = viewer_pc
            
            print(f"Created offer for viewer {viewer_id}")
            return {
                "sdp": viewer_pc.localDescription.sdp,
                "type": viewer_pc.localDescription.type
            }
            
        except Exception as e:
            print(f"Error handling viewer connection: {e}")
            return None
            
    async def handle_viewer_answer(self, viewer_id, answer):
        """Handle viewer's answer"""
        if viewer_id not in self.viewers:
            return False
            
        try:
            print(f"Processing answer from viewer {viewer_id}")
            viewer_pc = self.viewers[viewer_id]
            await viewer_pc.setRemoteDescription(RTCSessionDescription(
                sdp=answer["sdp"],
                type=answer["type"]
            ))
            return True
            
        except Exception as e:
            print(f"Error handling viewer answer: {e}")
            return False
            
    async def handle_viewer_ice_candidate(self, viewer_id, candidate):
        """Handle viewer's ICE candidate"""
        if viewer_id not in self.viewers:
            return False
            
        try:
            print(f"Processing ICE candidate from viewer {viewer_id}")
            viewer_pc = self.viewers[viewer_id]
            await viewer_pc.addIceCandidate(candidate)
            return True
            
        except Exception as e:
            print(f"Error handling viewer ICE candidate: {e}")
            return False
            
    def remove_viewer(self, viewer_id):
        """Remove a viewer"""
        if viewer_id in self.viewers:
            self.viewers[viewer_id].close()
            del self.viewers[viewer_id]
            print(f"Removed viewer {viewer_id}")
            
    def get_viewer_count(self):
        """Get number of current viewers"""
        return len(self.viewers) 