import json
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class ProgressEvent:
    """Represents a progress event in the agent workflow"""
    thread_id: str
    phase: str
    message: str
    timestamp: str
    tool_name: Optional[str] = None
    is_loading: bool = True
    metadata: Optional[Dict[str, Any]] = None

class ProgressManager:
    """
    Manages SSE progress events for agent workflows
    Thread-safe singleton pattern for managing progress across different threads
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._active_streams: Dict[str, threading.Event] = {}
            self._progress_data: Dict[str, ProgressEvent] = {}
            self._subscribers: Dict[str, list] = {}
            self._lock = threading.Lock()
            self._initialized = True
    
    def start_progress_stream(self, thread_id: str) -> None:
        """Start a new progress stream for a thread"""
        with self._lock:
            if thread_id not in self._active_streams:
                self._active_streams[thread_id] = threading.Event()
                self._subscribers[thread_id] = []
                print(f"[ProgressManager] Started progress stream for thread: {thread_id}")
    
    def emit_progress(self, thread_id: str, phase: str, message: str, 
                     tool_name: Optional[str] = None, is_loading: bool = True, 
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit a progress event for a specific thread"""
        with self._lock:
            if thread_id not in self._active_streams:
                print(f"[ProgressManager] Warning: No active stream for thread {thread_id}")
                print(f"[ProgressManager] Available streams: {list(self._active_streams.keys())}")
                print(f"[ProgressManager] Attempted to emit: {phase} - {message}")
                # Still create the event for potential future connections
                self._progress_data[thread_id] = ProgressEvent(
                    thread_id=thread_id,
                    phase=phase,
                    message=message,
                    timestamp=datetime.utcnow().isoformat(),
                    tool_name=tool_name,
                    is_loading=is_loading,
                    metadata=metadata
                )
                return
            
            progress_event = ProgressEvent(
                thread_id=thread_id,
                phase=phase,
                message=message,
                timestamp=datetime.utcnow().isoformat(),
                tool_name=tool_name,
                is_loading=is_loading,
                metadata=metadata
            )
            
            self._progress_data[thread_id] = progress_event
            print(f"[ProgressManager] Emitted progress for {thread_id}: {phase} - {message}")
    
    def get_progress_generator(self, thread_id: str):
        """Generator for SSE streaming"""
        def event_generator():
            self.start_progress_stream(thread_id)
            
            try:
                # Send initial connection event
                yield f"data: {json.dumps({'type': 'connected', 'thread_id': thread_id})}\n\n"
                
                # Keep connection alive and send progress updates
                last_check_time = datetime.utcnow()
                timeout_seconds = 300  # 5 minute timeout
                
                while thread_id in self._active_streams:
                    with self._lock:
                        if thread_id in self._progress_data:
                            progress_event = self._progress_data[thread_id]
                            event_data = {
                                'type': 'progress',
                                'thread_id': progress_event.thread_id,
                                'phase': progress_event.phase,
                                'message': progress_event.message,
                                'timestamp': progress_event.timestamp,
                                'tool_name': progress_event.tool_name,
                                'is_loading': progress_event.is_loading,
                                'metadata': progress_event.metadata
                            }
                            yield f"data: {json.dumps(event_data)}\n\n"
                            
                            # Clear the event after sending
                            del self._progress_data[thread_id]
                            last_check_time = datetime.utcnow()
                    
                    # Check for timeout
                    if (datetime.utcnow() - last_check_time).total_seconds() > timeout_seconds:
                        print(f"[ProgressManager] Timeout reached for thread {thread_id}, closing stream")
                        break
                    
                    threading.Event().wait(0.1)
                    
            except GeneratorExit:
                print(f"[ProgressManager] Client disconnected from thread: {thread_id}")
                self.end_progress_stream(thread_id)
            except Exception as e:
                print(f"[ProgressManager] Error in progress generator for {thread_id}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                self.end_progress_stream(thread_id)
        
        return event_generator()
    
    def end_progress_stream(self, thread_id: str) -> None:
        """End a progress stream and cleanup"""
        with self._lock:
            if thread_id in self._active_streams:
                del self._active_streams[thread_id]
                
            if thread_id in self._subscribers:
                del self._subscribers[thread_id]
                
            if thread_id in self._progress_data:
                del self._progress_data[thread_id]
                
            print(f"[ProgressManager] Ended progress stream for thread: {thread_id}")
    
    def complete_progress(self, thread_id: str, final_message: str = "✅ Done!") -> None:
        """Send completion event and end the stream"""
        self.emit_progress(
            thread_id=thread_id,
            phase="completed",
            message=final_message,
            is_loading=False
        )
        threading.Event().wait(0.2)
        self.end_progress_stream(thread_id)

progress_manager = ProgressManager() 