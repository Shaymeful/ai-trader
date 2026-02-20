#!/usr/bin/env python3
"""Check AI Copilot configuration status."""
import requests

response = requests.get('http://localhost:8001/api/ai-copilot/config')
config = response.json()

print("=" * 60)
print("AI CO-PILOT CONFIGURATION")
print("=" * 60)
print(f"Master Switch: {'ENABLED' if config['effective']['enabled'] else 'DISABLED'}")
print(f"Source: {config['sources']['enabled']}")
print(f"Trading Disabled: {config['trading_disabled_effective']}")
print()
print("Features:")
print(f"  Trade Rationale:        {'ON' if config['effective']['trade_rationale']['enabled'] else 'OFF'} (source: {config['sources']['trade_rationale']['enabled']})")
print(f"  Daily Journal:          {'ON' if config['effective']['daily_journal']['enabled'] else 'OFF'} (source: {config['sources']['daily_journal']['enabled']})")
print(f"  Strategy Critique:      {'ON' if config['effective']['strategy_critique']['enabled'] else 'OFF'} (source: {config['sources']['strategy_critique']['enabled']})")
print(f"  Sector Recommendations: {'ON' if config['effective']['sector_recommendations']['enabled'] else 'OFF'} (source: {config['sources']['sector_recommendations']['enabled']})")
print()
print("=" * 60)
print("CONFIGURATION FILE LOCATIONS:")
print("=" * 60)
print("  YAML config:    config/config.yaml")
print("  UI overrides:   data/ui_runtime_overrides.json")
print()
if config['effective']['enabled']:
    print("[OK] AI Co-Pilot is ENABLED and will run when loop starts")
else:
    print("[X] AI Co-Pilot is DISABLED - enable in config/config.yaml")
