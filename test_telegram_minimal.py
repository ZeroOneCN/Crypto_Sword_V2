#!/usr/bin/env python3
"""Minimal test: isolate whether Application.builder().build() hangs."""
import asyncio
import os
import sys
import time

# Load .env
env_path = "/root/.hermes/scripts/Crypto_Sword_V2/.env"
token = ""
chat_id = ""
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1]
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1]

if not token:
    print("NO TOKEN FOUND in .env — using fake token")
    token = "0000000000:AAAAAA_BBBBB_CCCCCCCCCCCCCCCCCC"

print(f"Token (first 15): {token[:15]}...")
print(f"Chat ID: {chat_id}")

# ---------------------------------------------------------
# Test 1: httpx raw request with timeout
# ---------------------------------------------------------
print("\n=== Test 1: httpx direct to api.telegram.org ===")
try:
    import httpx
    t0 = time.monotonic()
    url = f"https://api.telegram.org/bot{token}/getMe"
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url)
    elapsed = time.monotonic() - t0
    print(f"  Status: {r.status_code} (took {elapsed:.2f}s)")
    print(f"  Body: {r.text[:200]}")
except Exception as e:
    elapsed = time.monotonic() - t0
    print(f"  FAILED after {elapsed:.2f}s: {e}")

# ---------------------------------------------------------
# Test 2: Application.builder().build() with timer
# ---------------------------------------------------------
print("\n=== Test 2: Application.builder().build() ===")
try:
    from telegram import Update
    from telegram.ext import Application
    t0 = time.monotonic()
    print("  Building application...")
    app = Application.builder().token(token).build()
    elapsed = time.monotonic() - t0
    print(f"  SUCCESS: built in {elapsed:.2f}s")
    if app.bot.username:
        print(f"  Bot username: {app.bot.username}")
except Exception as e:
    elapsed = time.monotonic() - t0
    print(f"  FAILED after {elapsed:.2f}s: {type(e).__name__}: {e}")

# ---------------------------------------------------------
# Test 3: Check PTB default request parameters
# ---------------------------------------------------------
print("\n=== Test 3: PTB default request parameters ===")
try:
    from telegram.request import HTTPXRequest
    req = HTTPXRequest()
    print(f"  connect_timeout: {req._connect_timeout}")
    print(f"  read_timeout: {req._read_timeout}")
    print(f"  write_timeout: {req._write_timeout}")
    print(f"  pool_timeout: {req._pool_timeout}")
except Exception as e:
    print(f"  FAILED: {e}")

print("\nDone.")
