"""
Feishu Channel Plugin

Implements the ChannelPlugin interface for Feishu messaging platform.
Uses lark-oapi SDK with WebSocket long connection for event subscription.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger('tasknexus.plugins.feishu')


class FeishuChannel:
    """
    Feishu messaging channel plugin.
    
    Attributes:
        id: Channel identifier ('feishu')
        label: Human-readable name ('飞书')
    """
    
    # Maximum number of message IDs to track for deduplication
    MESSAGE_CACHE_SIZE = 1000
    
    def __init__(self):
        self.client = None
        self.ws_client = None
        self._message_callback: Optional[Callable] = None
        self._running = False
        self._config: Dict[str, Any] = {}
        self._ws_thread: Optional[threading.Thread] = None
        self._thread_error: Optional[Exception] = None
        self._thread_started = threading.Event()
        # Message deduplication: track recently processed message IDs
        self._processed_messages: set = set()
        self._message_cache_lock = threading.Lock()
    
    @property
    def id(self) -> str:
        return "feishu"
    
    @property
    def label(self) -> str:
        return "飞书"
    
    async def start(self, config: Dict[str, Any]) -> None:
        """
        Start the Feishu WebSocket connection for receiving events.
        
        Args:
            config: Configuration dict containing:
                - app_id: Feishu App ID
                - app_secret: Feishu App Secret
        """
        app_id = config.get('app_id')
        app_secret = config.get('app_secret')
        
        if not app_id or not app_secret:
            raise ValueError("Feishu app_id and app_secret are required")
        
        self._config = config
        self._running = True
        self._thread_error = None
        
        logger.info("Starting Feishu WebSocket connection...")
        
        # Store message callback reference for use in thread
        message_callback = self._message_callback
        channel_id = self.id
        
        # Run everything related to lark-oapi in a separate thread with its own event loop
        # This is because lark-oapi internally uses asyncio.get_event_loop() which
        # conflicts with the Django management command's event loop
        def run_ws_client():
            # Import lark-oapi only in this thread to avoid any module-level event loop capture
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
            
            try:
                # Build Lark client in this thread
                self.client = lark.Client.builder() \
                    .app_id(app_id) \
                    .app_secret(app_secret) \
                    .log_level(lark.LogLevel.INFO) \
                    .build()
                
                # Create event handler
                def handle_message_receive(data: P2ImMessageReceiveV1) -> None:
                    """Handle incoming message event"""
                    try:
                        event = data.event
                        message = event.message
                        sender = event.sender
                        message_id = message.message_id
                        
                        # Deduplicate: check if we've already processed this message
                        with self._message_cache_lock:
                            if message_id in self._processed_messages:
                                logger.debug(f"Skipping duplicate message: {message_id}")
                                return
                            
                            # Add to processed set
                            self._processed_messages.add(message_id)
                            
                            # Limit cache size to prevent memory growth
                            if len(self._processed_messages) > self.MESSAGE_CACHE_SIZE:
                                # Remove oldest entries (convert to list, remove first half)
                                to_remove = list(self._processed_messages)[:self.MESSAGE_CACHE_SIZE // 2]
                                for msg_id in to_remove:
                                    self._processed_messages.discard(msg_id)
                        
                        # Parse message content
                        content = ""
                        if message.message_type == "text":
                            content_json = json.loads(message.content)
                            content = content_json.get("text", "")
                        
                        # Import here to avoid circular dependency
                        from plugins.channel import ChannelMessage
                        
                        channel_message = ChannelMessage(
                            channel_id=channel_id,
                            chat_id=message.chat_id,
                            sender_id=sender.sender_id.open_id,
                            sender_name=sender.sender_id.open_id,  # Could fetch user info
                            content=content,
                            raw={
                                "message_id": message_id,
                                "message_type": message.message_type,
                                "create_time": message.create_time,
                            }
                        )
                        
                        # Call registered callback
                        if message_callback:
                            message_callback(channel_message)
                            
                    except Exception as e:
                        logger.exception(f"Error handling Feishu message: {e}")
                
                # Build event dispatcher
                event_handler = lark.EventDispatcherHandler.builder("", "") \
                    .register_p2_im_message_receive_v1(handle_message_receive) \
                    .build()
                
                # Create WebSocket client
                # Note: lark.ws.Client takes app_id, app_secret directly, not a lark.Client object
                self.ws_client = lark.ws.Client(
                    app_id=app_id,
                    app_secret=app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.INFO
                )
                
                # Signal that thread has started successfully
                self._thread_started.set()
                
                # This blocks until the connection ends
                self.ws_client.start()
                
            except Exception as e:
                logger.exception(f"WebSocket client error: {e}")
                self._thread_error = e
                self._thread_started.set()  # Signal even on error
        
        self._ws_thread = threading.Thread(target=run_ws_client, daemon=True)
        self._ws_thread.start()
        
        # Wait for thread to start or fail
        self._thread_started.wait(timeout=10)
        
        if self._thread_error:
            raise self._thread_error
        
        logger.info("Feishu WebSocket client started successfully")
        
        # Keep running
        while self._running:
            await asyncio.sleep(1)
            # Check if thread is still alive
            if not self._ws_thread.is_alive():
                logger.warning("WebSocket thread died unexpectedly")
                break
    
    async def stop(self) -> None:
        """Stop the Feishu WebSocket connection."""
        self._running = False
        if self.ws_client:
            # lark-oapi ws client doesn't have explicit stop, 
            # it stops when the process ends
            pass
        logger.info("Feishu channel stopped")
    
    async def send(self, payload) -> bool:
        """
        Send a message to Feishu.
        
        Args:
            payload: MessagePayload with chat_id and content
            
        Returns:
            True if sent successfully
        """
        if not self.client:
            logger.error("Feishu client not initialized")
            return False
        
        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
            
            content = json.dumps({"text": payload.content})
            
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                        .receive_id(payload.chat_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                ) \
                .build()
            
            response = self.client.im.v1.message.create(request)
            
            if not response.success():
                logger.error(f"Failed to send Feishu message: {response.msg}")
                return False
            
            logger.info(f"Sent Feishu message to {payload.chat_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error sending Feishu message: {e}")
            return False
    
    def on_message(self, callback: Callable) -> None:
        """
        Register callback for incoming messages.
        
        Args:
            callback: Function to call with ChannelMessage when received
        """
        self._message_callback = callback
