import cv2
import numpy as np
from PIL import Image, ImageTk
import threading
import asyncio
from aiortc import (
    MediaStreamTrack,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceServer,
    RTCConfiguration,
    RTCIceCandidate,
    RTCRtpSender
)
from av import VideoFrame  # Import VideoFrame from av package
import socket
import logging
from aiortc.contrib.media import MediaPlayer, MediaRecorder
import json
import queue
import time
import tkinter as tk
from aiortc import VideoStreamTrack as BaseVideoStreamTrack
import websockets
from fractions import Fraction

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
        self._init_camera()
        self._current_image = None
        self._display_window = None
        self._running = True
        self._frame_count = 0
        self._start_time = time.time()
        self._last_frame = None
        print("VideoStreamTrack initialized")
        
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
                            self._last_frame = rgb_frame  # Store first frame
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
        print("Stopping video track")  # Debug log
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
            print("Track has ended")
            raise Exception("Track has ended")
            
        try:
            # Capture frame
            ret, frame = self.cap.read()
            if not ret:
                print("Failed to capture frame, attempting to reinitialize camera")
                try:
                    self._init_camera()
                    ret, frame = self.cap.read()
                except Exception as e:
                    print(f"Failed to reinitialize camera: {e}")
                    if self._last_frame is not None:
                        frame = self._last_frame.copy()
                        ret = True
                    else:
                        raise Exception("No frame available")
                
            if ret:
                # Convert frame to RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._last_frame = frame.copy()
                
                # Update display if window is set
                if self._display_window:
                    try:
                        image = Image.fromarray(frame)
                        if image.size != (640, 480):
                            image = image.resize((640, 480), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(image=image)
                        self._current_image = photo
                        self._display_window.configure(image=photo)
                        self._display_window.image = photo
                    except Exception as e:
                        print(f"Error updating display: {e}")
                        
                # Create video frame
                video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
                
                # Calculate pts based on elapsed time (90kHz clock)
                elapsed_time = time.time() - self._start_time
                pts = int(elapsed_time * 90000)
                video_frame.pts = pts
                
                # Set time base as integer ratio (1/90000)
                video_frame.time_base = Fraction(1, 90000)
                
                self._frame_count += 1
                print(f"Sending frame #{self._frame_count} with pts={pts}, time_base={video_frame.time_base}")
                
                # Control frame rate
                await asyncio.sleep(1/30)
                
                return video_frame
            else:
                raise Exception("Failed to capture frame")
                
        except Exception as e:
            print(f"Error in recv: {e}")
            if self._last_frame is not None:
                video_frame = VideoFrame.from_ndarray(self._last_frame, format="rgb24")
                elapsed_time = time.time() - self._start_time
                pts = int(elapsed_time * 90000)
                video_frame.pts = pts
                video_frame.time_base = Fraction(1, 90000)
                print(f"Using last frame as fallback, pts={pts}")
                return video_frame
            raise

class SignalingServer:
    def __init__(self, stream_handler):
        self.stream_handler = stream_handler
        self.viewers = {}  # Store viewer websocket connections
        self.server = None
        self.pending_ice_candidates = {}  # Store pending ICE candidates

    def __call__(self, websocket, path=None):
        """Main WebSocket handler - this is called for each new connection"""
        return self._handle_connection(websocket)

    async def _handle_connection(self, websocket):
        """Handle the actual WebSocket connection"""
        viewer_id = None
        try:
            print("New viewer connection received")
            # Wait for join message with timeout
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)
                print(f"Received message: {data}")
                
                if data["type"] == "join":
                    viewer_id = data["viewer_id"]
                    print(f"Viewer {viewer_id} joined")
                    
                    # Store viewer websocket
                    self.viewers[viewer_id] = websocket
                    self.pending_ice_candidates[viewer_id] = []
                    
                    # Create offer for viewer
                    print(f"Creating offer for viewer {viewer_id}")
                    offer = await self.stream_handler.handle_viewer_connection(viewer_id)
                    
                    if not offer:
                        print(f"Failed to create offer for viewer {viewer_id}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Failed to create offer"
                        }))
                        return
                        
                    print(f"Sending offer to viewer {viewer_id}: {offer}")
                    await websocket.send(json.dumps({
                        "type": "offer",
                        "offer": offer
                    }))
                    
                    # Wait for answer with timeout
                    try:
                        print(f"Waiting for answer from viewer {viewer_id}")
                        message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        data = json.loads(message)
                        print(f"Received answer: {data}")
                        
                        if data["type"] == "answer":
                            print(f"Processing answer from viewer {viewer_id}")
                            success = await self.stream_handler.handle_viewer_answer(
                                viewer_id, data["answer"]
                            )
                            
                            if success:
                                print(f"Answer processed successfully for {viewer_id}")
                                # Send any pending ICE candidates
                                for candidate in self.pending_ice_candidates[viewer_id]:
                                    await websocket.send(json.dumps({
                                        "type": "ice_candidate",
                                        "candidate": candidate
                                    }))
                                
                                # Keep connection alive and handle ICE candidates
                                while True:
                                    try:
                                        message = await websocket.recv()
                                        data = json.loads(message)
                                        print(f"Received message from viewer: {data}")
                                        
                                        if data["type"] == "ice_candidate" and data.get("candidate"):
                                            print(f"Processing ICE candidate from viewer {viewer_id}")
                                            await self.stream_handler.handle_viewer_ice_candidate(
                                                viewer_id, data["candidate"]
                                            )
                                    except websockets.exceptions.ConnectionClosed:
                                        print(f"Viewer {viewer_id} connection closed")
                                        break
                                    except Exception as e:
                                        print(f"Error handling ICE candidate: {e}")
                                        break
                            else:
                                print(f"Failed to process answer for {viewer_id}")
                                await websocket.send(json.dumps({
                                    "type": "error",
                                    "message": "Failed to process answer"
                                }))
                                
                    except asyncio.TimeoutError:
                        print(f"Timeout waiting for answer from viewer {viewer_id}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Timeout waiting for answer"
                        }))
                    except Exception as e:
                        print(f"Error handling viewer answer: {e}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": str(e)
                        }))
                else:
                    print("Invalid message type")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid message type"
                    }))
                    
            except asyncio.TimeoutError:
                print("Timeout waiting for join message")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Timeout waiting for join message"
                }))
            except json.JSONDecodeError:
                print("Invalid JSON message")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON message"
                }))
            except Exception as e:
                print(f"Error handling initial message: {e}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"Viewer connection closed unexpectedly")
        except Exception as e:
            print(f"Error in handle_viewer: {e}")
            if websocket and websocket.open:
                try:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))
                except:
                    pass
        finally:
            # Clean up viewer connection
            if viewer_id:
                self.viewers.pop(viewer_id, None)
                self.pending_ice_candidates.pop(viewer_id, None)
                await self.stream_handler.remove_viewer(viewer_id)
                print(f"Cleaned up viewer {viewer_id} connection")

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
        self.signaling_server = None
        self.server_task = None
        self.chat_client = None  # Reference to chat client
        self.server = None  # Store WebSocket server instance
        self.viewer_count = 0  # Track number of viewers
        self.viewer_callback = None  # Callback for updating viewer count in UI
        
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
        
    def set_viewer_callback(self, callback):
        """Set callback for viewer count updates"""
        self.viewer_callback = callback
        
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
            
            # Start signaling server
            print("Starting signaling server...")
            self.signaling_server = SignalingServer(self)
            
            # Get local IP address for streaming
            local_ip = get_local_ip()
            print(f"Local IP for streaming: {local_ip}")
            
            # Create and start the WebSocket server
            try:
                # Create server
                server = await websockets.serve(
                    self.signaling_server,  # Use the SignalingServer instance directly
                    "0.0.0.0",  # Listen on all interfaces
                    8765,
                    ping_interval=None,  # Disable ping to prevent timeouts
                    ping_timeout=None,
                    close_timeout=10  # Add close timeout
                )
                print("WebSocket server created successfully")
                
                # Store server instance
                self.server = server
                
                # Keep server running in the background
                loop = asyncio.get_event_loop()
                self.server_task = loop.create_task(server.wait_closed())
                print("WebSocket server started and running")
                
                # Wait a moment to ensure server is ready
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Failed to start WebSocket server: {e}")
                raise Exception(f"Failed to start WebSocket server: {str(e)}")
            
            self.is_streaming = True
            print(f"Stream started successfully in channel: {self.channel}")
            
            # Notify central server about active stream with IP address
            if self.channel and self.streamer and self.token and self.chat_client:
                request = {
                    "type": "STREAM_START",
                    "token": self.token,
                    "channel": self.channel,
                    "streamer_ip": local_ip  # Include streamer's IP
                }
                response = self.chat_client._send_to_central_server(request)
                if not response.get("success"):
                    print(f"Failed to notify server about stream: {response.get('message')}")
                    return False
                
                # Verify the stream was registered with the IP
                stream_info = response.get("stream_info", {})
                if not stream_info.get("streamer_ip"):
                    print("Warning: Stream registered but IP address was not confirmed")
                else:
                    print(f"Stream registered with IP: {stream_info['streamer_ip']}")
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
        try:
            # Stop video track first
            if self.video_track:
                self.video_track.stop()
                self.video_track = None
            
            # Close all viewer connections
            for viewer_id, viewer_data in list(self.viewers.items()):
                try:
                    viewer_pc = viewer_data["pc"]
                    viewer_track = viewer_data["track"]
                    
                    # Stop the viewer's track first
                    if viewer_track:
                        viewer_track.stop()
                    
                    # Close the peer connection
                    if viewer_pc:
                        await viewer_pc.close()
                    
                    # Remove from viewers dictionary
                    del self.viewers[viewer_id]
                    print(f"Removed viewer {viewer_id}")
                    
                except Exception as e:
                    print(f"Error removing viewer {viewer_id}: {e}")
                    # Still try to remove from dictionary even if cleanup fails
                    self.viewers.pop(viewer_id, None)
            
            # Close main peer connection
            if self.pc:
                await self.pc.close()
                self.pc = None
            
            # Stop WebSocket server
            if self.server:
                self.server.close()
                if self.server_task:
                    try:
                        await asyncio.wait_for(self.server_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        print("Timeout waiting for server to close")
                    except Exception as e:
                        print(f"Error waiting for server to close: {e}")
                self.server = None
                self.server_task = None
            
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
            
        except Exception as e:
            print(f"Error in stop_stream: {e}")
            raise
            
    async def remove_viewer(self, viewer_id):
        """Remove a viewer"""
        if viewer_id in self.viewers:
            try:
                viewer_data = self.viewers[viewer_id]
                viewer_pc = viewer_data["pc"]
                viewer_track = viewer_data["track"]
                
                # Stop the viewer's track first
                if viewer_track:
                    viewer_track.stop()
                
                # Close the peer connection
                if viewer_pc:
                    await viewer_pc.close()
                
                # Remove from viewers dictionary
                del self.viewers[viewer_id]
                
                # Decrement viewer count
                self.viewer_count = max(0, self.viewer_count - 1)
                if self.viewer_callback:
                    self.viewer_callback(self.viewer_count)
                    
                print(f"Removed viewer {viewer_id}, viewer count decreased to {self.viewer_count}")
                
            except Exception as e:
                print(f"Error removing viewer {viewer_id}: {e}")
                # Still try to remove from dictionary even if cleanup fails
                self.viewers.pop(viewer_id, None)
                
                # Ensure viewer count is updated
                self.viewer_count = len(self.viewers)
                if self.viewer_callback:
                    self.viewer_callback(self.viewer_count)

    async def handle_viewer_connection(self, viewer_id):
        """Handle a new viewer connection"""
        if not self.is_streaming:
            print("Cannot handle viewer connection - stream not active")
            return None
            
        try:
            print(f"Handling viewer connection for {viewer_id}")
            
            # Verify video track is available
            if not self.video_track:
                print("Error: No video track available")
                return None
                
            # Create peer connection for viewer
            viewer_pc = RTCPeerConnection(configuration=self.config)
            
            # Create a new video track for this viewer
            class ViewerVideoTrack(MediaStreamTrack):
                kind = "video"
                
                def __init__(self, original_track):
                    super().__init__()
                    self.original_track = original_track
                    self._running = True
                    self._start_time = time.time()
                    
                async def recv(self):
                    if not self._running:
                        raise Exception("Track has ended")
                    try:
                        frame = await self.original_track.recv()
                        if frame:
                            # Calculate pts based on elapsed time (90kHz clock)
                            pts = int((time.time() - self._start_time) * 90000)
                            frame.pts = pts
                            frame.time_base = Fraction(1, 90000)  # Set time base
                            return frame
                        else:
                            print("Received empty frame from original track")
                            raise Exception("Empty frame received")
                    except Exception as e:
                        print(f"Error receiving frame in viewer track: {e}")
                        raise
                        
                def stop(self):
                    self._running = False
                    super().stop()
            
            # Create a new track instance for this viewer
            viewer_track = ViewerVideoTrack(self.video_track)
            
            # Add the video track to the peer connection
            sender = viewer_pc.addTrack(viewer_track)
            
            # Configure the transceiver to be sendonly
            for transceiver in viewer_pc.getTransceivers():
                if transceiver.sender == sender:
                    transceiver.direction = "sendonly"
                    break
                    
            print(f"Video track added for {viewer_id}")
            
            # Set up negotiation needed handler
            @viewer_pc.on("negotiationneeded")
            async def on_negotiation_needed():
                print(f"Negotiation needed for viewer {viewer_id}")
                try:
                    await viewer_pc.setLocalDescription(await viewer_pc.createOffer())
                except Exception as e:
                    print(f"Error in negotiation for viewer {viewer_id}: {e}")
            
            # Set up ICE candidate handler
            @viewer_pc.on("icecandidate")
            async def on_ice_candidate(event):
                if event.candidate:
                    print(f"Generated ICE candidate for viewer {viewer_id}: {event.candidate}")
                    if viewer_id in self.viewers:
                        try:
                            websocket = self.signaling_server.viewers.get(viewer_id)
                            if websocket and websocket.open:
                                candidate_data = {
                                    "candidate": event.candidate.candidate,
                                    "sdpMid": event.candidate.sdpMid,
                                    "sdpMLineIndex": event.candidate.sdpMLineIndex
                                }
                                print(f"Sending ICE candidate to viewer {viewer_id}: {candidate_data}")
                                await websocket.send(json.dumps({
                                    "type": "ice_candidate",
                                    "candidate": candidate_data
                                }))
                            else:
                                # Store candidate for later if websocket is not ready
                                self.signaling_server.pending_ice_candidates[viewer_id].append({
                                    "candidate": event.candidate.candidate,
                                    "sdpMid": event.candidate.sdpMid,
                                    "sdpMLineIndex": event.candidate.sdpMLineIndex
                                })
                        except Exception as e:
                            print(f"Error sending ICE candidate to viewer {viewer_id}: {e}")
            
            # Set up connection state change handler
            @viewer_pc.on("connectionstatechange")
            async def on_connectionstatechange():
                print(f"Connection state change for viewer {viewer_id}: {viewer_pc.connectionState}")
                if viewer_pc.connectionState == "connected":
                    # Increment viewer count when connection is established
                    self.viewer_count += 1
                    if self.viewer_callback:
                        self.viewer_callback(self.viewer_count)
                    print(f"Viewer count increased to {self.viewer_count}")
                elif viewer_pc.connectionState == "failed" or viewer_pc.connectionState == "closed":
                    await self.remove_viewer(viewer_id)
            
            # Create offer
            print(f"Creating offer for viewer {viewer_id}")
            try:
                offer = await viewer_pc.createOffer()
                await viewer_pc.setLocalDescription(offer)
                print(f"Local description set for {viewer_id}")
            except Exception as e:
                print(f"Error creating offer: {e}")
                await viewer_pc.close()
                return None
            
            # Store viewer connection and track
            self.viewers[viewer_id] = {
                "pc": viewer_pc,
                "track": viewer_track
            }
            
            print(f"Created offer for viewer {viewer_id}")
            return {
                "sdp": viewer_pc.localDescription.sdp,
                "type": viewer_pc.localDescription.type
            }
            
        except Exception as e:
            print(f"Error handling viewer connection: {e}")
            # Clean up on error
            if viewer_id in self.viewers:
                await self.remove_viewer(viewer_id)
            return None
            
    async def handle_viewer_answer(self, viewer_id, answer):
        """Handle viewer's answer"""
        if viewer_id not in self.viewers:
            print(f"No viewer connection found for {viewer_id}")
            return False
            
        try:
            print(f"Processing answer from viewer {viewer_id}: {answer}")
            viewer_pc = self.viewers[viewer_id]["pc"]
            await viewer_pc.setRemoteDescription(RTCSessionDescription(
                sdp=answer["sdp"],
                type=answer["type"]
            ))
            print(f"Remote description set for viewer {viewer_id}")
            return True
            
        except Exception as e:
            print(f"Error handling viewer answer: {e}")
            await self.remove_viewer(viewer_id)
            return False
            
    async def handle_viewer_ice_candidate(self, viewer_id, candidate):
        """Handle viewer's ICE candidate"""
        if viewer_id not in self.viewers:
            print(f"No viewer connection found for {viewer_id}")
            return False
            
        try:
            print(f"Processing ICE candidate from viewer {viewer_id}: {candidate}")
            viewer_pc = self.viewers[viewer_id]["pc"]
            await viewer_pc.addIceCandidate(RTCIceCandidate(
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                candidate=candidate.get("candidate")
            ))
            print(f"ICE candidate added for viewer {viewer_id}")
            return True
            
        except Exception as e:
            print(f"Error handling viewer ICE candidate: {e}")
            await self.remove_viewer(viewer_id)
            return False
            
    def get_viewer_count(self):
        """Get number of current viewers"""
        return len(self.viewers) 