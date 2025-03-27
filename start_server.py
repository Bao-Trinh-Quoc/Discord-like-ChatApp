#!/usr/bin/env python3
"""
Central Server Launcher Script

This script provides a convenient way to start the central server
for the Discord-like chat application.
"""

import os
import sys
import argparse
from centralized_server import CentralServer, get_local_ip

def main():
    parser = argparse.ArgumentParser(
                prog='Launch Central Server',
                description='Centralized tracker for chat application',
                epilog='This server manages peer registration and channel coordination')
    
    parser.add_argument('--host', default=get_local_ip())
    parser.add_argument('--port', type=int, default=8000)
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Starting Central Server for Discord-like Chat Application  ".center(60))
    print("=" * 60)
    print(f"Server will listen on {args.host}:{args.port}")
    print("Press Ctrl+C to stop the server")
    print()
    
    server = CentralServer(args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()
        print("Server stopped.")

if __name__ == "__main__":
    # Make script executable
    if sys.platform != "win32":
        script_path = os.path.abspath(__file__)
        if not os.access(script_path, os.X_OK):
            os.chmod(script_path, 0o755)
    
    main()