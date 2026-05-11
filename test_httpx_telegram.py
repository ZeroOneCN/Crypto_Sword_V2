#!/usr/bin/env python3
"""Integration test: raw httpx TelegramBot with send_message."""
import asyncio
import os
import sys
import time

# Add project to path
sys.path.insert(0, "/root/.hermes/scripts/Crypto_Sword_V2")

# Load .env for token/chat_id
env_path = "/root/.hermes/scripts/Crypto_Sword_V2/.env"
token = ""
chat_id = ""
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()

print(f"Token prefix: {token[:20]}...")
print(f"Chat ID: {chat_id}")

async def main():
    from cryptopilot.notification.telegram_bot import TelegramBot

    bot = TelegramBot(token=token, chat_id=chat_id)

    t0 = time.monotonic()
    print("\n1. Starting bot (getMe verification)...")
    await bot.start()
    t1 = time.monotonic()
    print(f"   Started in {t1 - t0:.2f}s")
    print(f"   Running: {bot._running}")

    t0 = time.monotonic()
    print("\n2. Sending test message...")
    await bot.send_message(
        "<b>🧪 CryptoPilot V2 测试</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Telegram Bot 已切换为 <code>httpx</code> 直连模式\n"
        "⏱ 初始化速度: &lt;10s\n"
        "📡 无需 python-telegram-bot 依赖"
    )
    t1 = time.monotonic()
    print(f"   Sent in {t1 - t0:.2f}s")

    t0 = time.monotonic()
    print("\n3. Stopping bot...")
    await bot.stop()
    t1 = time.monotonic()
    print(f"   Stopped in {t1 - t0:.2f}s")

    print("\n✅ ALL TESTS PASSED")

asyncio.run(main())
