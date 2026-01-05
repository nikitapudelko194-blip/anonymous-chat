#!/usr/bin/env python3
"""Entry point for running the bot.

This module serves as the main entry point for the anonymous chat bot.
It initializes and starts the bot with all necessary handlers and middleware.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import main bot function from bot.main
try:
    from bot.main import main as bot_main
except ImportError as e:
    print(f"❌ Error importing bot.main: {e}")
    print("Make sure bot/main.py exists and is properly configured.")
    sys.exit(1)


async def main():
    """Main async entry point.
    
    This function calls the bot_main function which contains all the bot logic,
    database initialization, dispatcher setup, and polling.
    """
    try:
        # Start the bot
        await bot_main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("🚀 Starting Anonymous Chat Bot...")
    asyncio.run(main())
