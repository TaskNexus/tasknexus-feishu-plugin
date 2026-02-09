"""
Feishu Channel Plugin

Implements the ChannelPlugin interface for Feishu messaging platform.
Uses lark-oapi SDK with WebSocket long connection for event subscription.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger('tasknexus.plugins.feishu')


class FeishuChannel:
    """
    Feishu messaging channel plugin.
    
    Attributes:
        id: Channel identifier ('feishu')
        label: Human-readable name ('飞书')
    """
    
    def __init__(self):
        self.client = None
        self.ws_client = None
        self._message_callback: Optional[Callable] = None
        self._running = False
        self._config: Dict[str, Any] = {}
    
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
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        
        app_id = config.get('app_id')
        app_secret = config.get('app_secret')
        
        if not app_id or not app_secret:
            raise ValueError("Feishu app_id and app_secret are required")
        
        self._config = config
        
        # Build Lark client
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
                
                # Parse message content
                content = ""
                if message.message_type == "text":
                    content_json = json.loads(message.content)
                    content = content_json.get("text", "")
                
                # Import here to avoid circular dependency
                from plugins.channel import ChannelMessage
                
                channel_message = ChannelMessage(
                    channel_id=self.id,
                    chat_id=message.chat_id,
                    sender_id=sender.sender_id.open_id,
                    sender_name=sender.sender_id.open_id,  # Could fetch user info
                    content=content,
                    raw={
                        "message_id": message.message_id,
                        "message_type": message.message_type,
                        "create_time": message.create_time,
                    }
                )
                
                # Call registered callback
                if self._message_callback:
                    self._message_callback(channel_message)
                    
            except Exception as e:
                logger.exception(f"Error handling Feishu message: {e}")
        
        # Build event dispatcher
        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(handle_message_receive) \
            .build()
        
        # Start WebSocket client
        self._running = True
        self.ws_client = lark.ws.Client(
            self.client,
            event_handler,
            log_level=lark.LogLevel.INFO
        )
        
        logger.info(f"Starting Feishu WebSocket connection...")
        
        # Run in background
        self.ws_client.start()
        
        # Keep running
        while self._running:
            await asyncio.sleep(1)
    
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
