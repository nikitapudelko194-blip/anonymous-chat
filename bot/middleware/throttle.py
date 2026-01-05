"""Throttle middleware for rate limiting user messages"""

import time
from typing import Any, Callable, Dict, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message


class ThrottleMiddleware(BaseMiddleware):
    """Middleware to prevent spam by rate limiting messages"""
    
    def __init__(self, rate_limit: float = 1):
        """Initialize throttle middleware
        
        Args:
            rate_limit: Minimum seconds between messages (default 1 second)
        """
        self.rate_limit = rate_limit
        self.last_message = {}  # user_id -> timestamp

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        """Process message with throttling"""
        # Get user_id if message has from_user
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id
        else:
            return await handler(event, data)
        
        now = time.time()
        
        # Check if user sent message too fast
        if user_id in self.last_message:
            time_diff = now - self.last_message[user_id]
            if time_diff < self.rate_limit:
                # Ignore message if sent too quickly
                return None
        
        # Update last message time
        self.last_message[user_id] = now
        
        # Call handler
        return await handler(event, data)
