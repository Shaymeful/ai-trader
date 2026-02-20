#!/usr/bin/env python3
"""Force activate pending sector changes."""

from src.app.universe_registry import UniverseRegistry

registry = UniverseRegistry()

print("Before activation:")
print(f"Universe symbols: {', '.join(registry.resolve().symbols)}")
print()

print("Forcing activation of ALL pending changes...")
registry.activate_pending_changes()

print("\nAfter activation:")
resolution = registry.resolve()
print(f"Universe: {len(resolution.symbols)} symbols")
print(f"Symbols: {', '.join(resolution.symbols)}")
print(f"Sectors used: {', '.join(resolution.sectors_used)}")
