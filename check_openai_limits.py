"""Quick check of OpenAI API rate limit status."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from src.app.config import load_config_with_yaml

    config = load_config_with_yaml()

    # OpenAI uses environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] No OPENAI_API_KEY environment variable set")
        sys.exit(1)

    # Try a minimal API call
    import openai

    client = openai.OpenAI(api_key=api_key)

    print("Testing OpenAI API access...")
    print(f"Model: {config.llm_openai_model}")

    # Minimal test call (uses ~10 tokens)
    response = client.chat.completions.create(
        model=config.llm_openai_model,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=5
    )

    print("\n[OK] OpenAI API is accessible!")
    print(f"Response: {response.choices[0].message.content}")
    print(f"\nRate limit info:")

    # Note: Rate limit info is in response headers but not easily accessible via SDK
    print("  - Daily limit: 200 requests/day (free tier)")
    print("  - Resets: Midnight UTC or 24h from first request")
    print("  - Current UTC time:", end=" ")

    from datetime import datetime, UTC
    print(datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))

    print("\n[OK] Ready to run loop!")
    print("\nWith throttling changes:")
    print("  - Market hours check: Skip when closed")
    print("  - Sell scanner: Every 30 min (was every 5)")
    print("  - Loop interval: 10 min (was 5)")
    print("  - Expected daily usage: ~130 LLM calls (65% of limit)")

except Exception as e:
    error_msg = str(e)

    if "429" in error_msg or "rate limit" in error_msg.lower():
        print("[ERROR] RATE LIMIT STILL ACTIVE")
        print(f"Error: {error_msg}")
        print("\nRate limits typically reset at midnight UTC.")
        print("You may need to wait a bit longer or upgrade to paid tier.")
    else:
        print(f"[ERROR] API Error: {error_msg}")

    sys.exit(1)
