#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🧪 Скрипт для проверки правильности структуры модулей
Запустите из корня проекта: python test_imports.py
"""

import sys
import os

print("\n" + "="*60)
print("🧪 ПРОВЕРКА СТРУКТУРЫ МОДУЛЕЙ")
print("="*60 + "\n")

# 1. Проверка текущей директории
print("📍 Текущая директория:")
cwd = os.getcwd()
print(f"   {cwd}")
if not cwd.endswith('anonymous-chat-main'):
    print("   ⚠️  ВНИМАНИЕ: Убедитесь что запускаете из корня проекта!\n")
else:
    print("   ✅ Правильная директория\n")

# 2. Проверка существования файлов
print("📁 Проверка файлов:")
required_files = [
    ('bot/__init__.py', 'Package init file'),
    ('bot/main.py', 'Main entry point'),
    ('bot/config.py', 'Configuration'),
    ('.env', 'Environment variables'),
]

for file_path, description in required_files:
    exists = os.path.exists(file_path)
    status = "✅" if exists else "❌"
    print(f"   {status} {file_path:30} ({description})")

print()

# 3. Проверка BOT_TOKEN
print("🔐 Проверка BOT_TOKEN:")
try:
    with open('.env', 'r', encoding='utf-8') as f:
        env_content = f.read()
        if 'BOT_TOKEN=' in env_content:
            print("   ✅ BOT_TOKEN найден в .env")
            if env_content.split('BOT_TOKEN=')[1].split('\n')[0].strip():
                print("   ✅ BOT_TOKEN имеет значение\n")
            else:
                print("   ❌ BOT_TOKEN пуст!\n")
        else:
            print("   ❌ BOT_TOKEN не найден в .env\n")
except FileNotFoundError:
    print("   ❌ .env файл не найден\n")

# 4. Попытка импорта модулей
print("🔌 Проверка импортов:")

try:
    print("   Пытаемся импортировать bot.config...")
    from bot.config import BOT_TOKEN, DB_PATH
    print("   ✅ Успешно импортирован bot.config")
    print(f"      BOT_TOKEN установлен: {bool(BOT_TOKEN)}")
    print(f"      DB_PATH: {DB_PATH}\n")
except ImportError as e:
    print(f"   ❌ Ошибка импорта: {e}\n")
except Exception as e:
    print(f"   ❌ Неожиданная ошибка: {e}\n")

# 5. Проверка aiogram
print("📦 Проверка зависимостей:")
required_packages = ['aiogram', 'python_dotenv', 'aiohttp', 'sqlalchemy']

for package in required_packages:
    try:
        __import__(package)
        print(f"   ✅ {package:20} установлен")
    except ImportError:
        print(f"   ❌ {package:20} НЕ установлен")
        print(f"      Установите: pip install {package}")

print()
print("="*60)
print("\n✅ ГОТОВО!\n")
print("Если все проверки прошли успешно, вы можете запустить:")
print("   python -m bot.main")
print("\nИли:")
print("   python bot/main.py")
print()
print("="*60 + "\n")
