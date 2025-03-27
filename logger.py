import os
import time
from datetime import datetime

class Logger:
    def __init__(self, log_file="system_log.txt", max_records=10000):
        self.log_file = log_file
        self.max_records = max_records
        self.record_count = 0
        self._initialize_log()
    
    def _initialize_log(self):
        """Initialize log file if it doesn't exist or count records if it does"""
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r') as f:
                self.record_count = sum(1 for _ in f)
        else:
            with open(self.log_file, 'w') as f:
                f.write(f"Log initialized at {datetime.now()}\n")
                self.record_count = 1
    
    def log_connection(self, source_ip, source_port, dest_ip, dest_port, connection_type):
        """Log a connection event"""
        self._log_event(f"CONNECTION: {source_ip}:{source_port} -> {dest_ip}:{dest_port} ({connection_type})")
    
    def log_data_transfer(self, source_ip, source_port, dest_ip, dest_port, data_size, direction):
        """Log a data transfer event"""
        self._log_event(f"DATA TRANSFER: {source_ip}:{source_port} {direction} {dest_ip}:{dest_port}, Size: {data_size} bytes")
    
    def log_auth(self, username, success, ip_address):
        """Log an authentication event"""
        result = "SUCCESS" if success else "FAILED"
        self._log_event(f"AUTH: {username} {result} from {ip_address}")
    
    def log_channel_event(self, channel_name, event_type, user=None):
        """Log channel-related events"""
        user_info = f" by {user}" if user else ""
        self._log_event(f"CHANNEL: {channel_name} {event_type}{user_info}")
    
    def log_message(self, channel_name, username, message_id):
        """Log message events"""
        self._log_event(f"MESSAGE: {username} in {channel_name}, ID: {message_id}")
    
    def _log_event(self, message):
        """Internal method to log events and manage log size"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
        
        self.record_count += 1
        
        # Check if we need to clear older records
        if self.record_count > self.max_records:
            self._rotate_log()
    
    def _rotate_log(self):
        """Keep the log file under the maximum number of records"""
        temp_file = f"{self.log_file}.tmp"
        
        with open(self.log_file, 'r') as original, open(temp_file, 'w') as temp:
            # Skip the oldest records
            for _ in range(self.record_count - self.max_records // 2):
                next(original)
            
            # Write the remaining records to the temp file
            temp.write(f"Log rotated at {datetime.now()} - Older records removed\n")
            for line in original:
                temp.write(line)
        
        # Replace the original file with the temp file
        os.replace(temp_file, self.log_file)
        
        # Update record count
        with open(self.log_file, 'r') as f:
            self.record_count = sum(1 for _ in f)

# Singleton instance
system_logger = Logger()