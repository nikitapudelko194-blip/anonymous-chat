#!/usr/bin/env python3
"""\n🚠 Anonymous Chat Bot - Основной файл запуска
"""

import sys
from pathlib import Path

# Добавить проект в path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    from bot.__main__ import main
    import asyncio
    asyncio.run(main())
