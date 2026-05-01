#!/usr/bin/env python3
"""
Post-installation script to ensure Playwright browsers are installed.
Run after: poetry install
"""

import subprocess
import sys
from pathlib import Path

def ensure_playwright_browsers():
    """Ensure Playwright browsers are installed."""
    try:
        print("🔍 Checking Playwright browser installation...")
        
        # Try to run a simple browser check
        result = subprocess.run(
            ["python", "-c", "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().close()"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print("✅ Playwright browsers already installed")
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass
    
    # Install browsers if check failed
    print("📦 Installing Playwright browsers...")
    try:
        subprocess.run(
            ["playwright", "install", "chromium"],
            check=True,
            capture_output=False
        )
        print("✅ Playwright browsers installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Failed to install Playwright browsers: {e}")
        print("   Run: poetry run playwright install chromium")
        return False

if __name__ == "__main__":
    success = ensure_playwright_browsers()
    sys.exit(0 if success else 1)
