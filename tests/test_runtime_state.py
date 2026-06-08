"""Tests for runtime state management (loop timing tracking)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.app.state import RuntimeState, load_runtime_state, save_runtime_state


def test_runtime_state_creation():
    """Test RuntimeState model creation with defaults."""
    state = RuntimeState(updated_at=datetime.now(UTC).isoformat())

    assert state.loop_interval_seconds == 3600  # Default 1 hour
    assert state.last_loop_start is None
    assert state.last_loop_end is None
    assert state.next_loop_at is None
    assert state.updated_at is not None


def test_runtime_state_with_values():
    """Test RuntimeState model creation with all values."""
    now = datetime.now(UTC)
    next_loop = now + timedelta(seconds=3600)

    state = RuntimeState(
        loop_interval_seconds=7200,
        last_loop_start=now.isoformat(),
        last_loop_end=(now + timedelta(seconds=10)).isoformat(),
        next_loop_at=next_loop.isoformat(),
        updated_at=now.isoformat(),
    )

    assert state.loop_interval_seconds == 7200
    assert state.last_loop_start == now.isoformat()
    assert state.last_loop_end == (now + timedelta(seconds=10)).isoformat()
    assert state.next_loop_at == next_loop.isoformat()
    assert state.updated_at == now.isoformat()


def test_load_runtime_state_nonexistent():
    """Test loading runtime state when file doesn't exist."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        state = load_runtime_state(str(state_dir))

        # Should return default state
        assert state.loop_interval_seconds == 3600
        assert state.last_loop_start is None
        assert state.last_loop_end is None
        assert state.next_loop_at is None
        assert state.updated_at is not None  # Should have timestamp


def test_save_and_load_runtime_state():
    """Test saving and loading runtime state."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        # Create state
        now = datetime.now(UTC)
        original_state = RuntimeState(
            loop_interval_seconds=7200,
            last_loop_start=now.isoformat(),
            last_loop_end=(now + timedelta(seconds=10)).isoformat(),
            next_loop_at=(now + timedelta(seconds=7200)).isoformat(),
            updated_at=now.isoformat(),
        )

        # Save state
        save_runtime_state(original_state, str(state_dir))

        # Verify file exists
        runtime_file = state_dir / "runtime.json"
        assert runtime_file.exists()

        # Load state
        loaded_state = load_runtime_state(str(state_dir))

        # Verify values match (updated_at may have changed during save)
        assert loaded_state.loop_interval_seconds == 7200
        assert loaded_state.last_loop_start == now.isoformat()
        assert loaded_state.last_loop_end == (now + timedelta(seconds=10)).isoformat()
        assert loaded_state.next_loop_at == (now + timedelta(seconds=7200)).isoformat()


def test_save_runtime_state_updates_timestamp():
    """Test that saving runtime state updates the updated_at timestamp."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        # Create state with old timestamp
        old_time = datetime.now(UTC) - timedelta(hours=1)
        state = RuntimeState(
            loop_interval_seconds=3600,
            last_loop_start=old_time.isoformat(),
            updated_at=old_time.isoformat(),
        )

        # Save state
        save_runtime_state(state, str(state_dir))

        # Load and check timestamp was updated
        loaded_state = load_runtime_state(str(state_dir))
        loaded_time = datetime.fromisoformat(loaded_state.updated_at.replace("Z", "+00:00"))
        time_diff = datetime.now(UTC) - loaded_time

        # Timestamp should be recent (within last 2 seconds)
        assert time_diff.total_seconds() < 2.0


def test_load_runtime_state_corrupted_json():
    """Test loading runtime state with corrupted JSON file."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        runtime_file = state_dir / "runtime.json"

        # Write corrupted JSON
        runtime_file.write_text("{ invalid json }")

        # Should return default state instead of crashing
        state = load_runtime_state(str(state_dir))

        assert state.loop_interval_seconds == 3600
        assert state.last_loop_start is None


def test_save_runtime_state_atomic():
    """Test that save_runtime_state uses atomic write (temp file + rename)."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        state = RuntimeState(loop_interval_seconds=3600, updated_at=datetime.now(UTC).isoformat())

        # Save state
        save_runtime_state(state, str(state_dir))

        runtime_file = state_dir / "runtime.json"
        assert runtime_file.exists()

        # Verify no .tmp files left behind
        tmp_files = list(state_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


def test_runtime_state_file_format():
    """Test that runtime state file has correct JSON format."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        now = datetime.now(UTC)
        state = RuntimeState(
            loop_interval_seconds=7200,
            last_loop_start=now.isoformat(),
            last_loop_end=(now + timedelta(seconds=10)).isoformat(),
            next_loop_at=(now + timedelta(seconds=7200)).isoformat(),
            updated_at=now.isoformat(),
        )

        save_runtime_state(state, str(state_dir))

        # Read and verify JSON structure
        runtime_file = state_dir / "runtime.json"
        with open(runtime_file) as f:
            data = json.load(f)

        assert "loop_interval_seconds" in data
        assert "last_loop_start" in data
        assert "last_loop_end" in data
        assert "next_loop_at" in data
        assert "updated_at" in data

        assert data["loop_interval_seconds"] == 7200
        assert data["last_loop_start"] == now.isoformat()


def test_runtime_state_multiple_saves():
    """Test multiple sequential saves to same file."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)

        # First save
        state1 = RuntimeState(
            loop_interval_seconds=3600,
            last_loop_start=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
        save_runtime_state(state1, str(state_dir))

        # Second save (update)
        now2 = datetime.now(UTC) + timedelta(hours=1)
        state2 = RuntimeState(
            loop_interval_seconds=3600,
            last_loop_start=state1.last_loop_start,
            last_loop_end=now2.isoformat(),
            next_loop_at=(now2 + timedelta(seconds=3600)).isoformat(),
            updated_at=now2.isoformat(),
        )
        save_runtime_state(state2, str(state_dir))

        # Load and verify latest values
        loaded = load_runtime_state(str(state_dir))

        assert loaded.last_loop_start == state1.last_loop_start
        assert loaded.last_loop_end == now2.isoformat()
        assert loaded.next_loop_at == (now2 + timedelta(seconds=3600)).isoformat()


def test_runtime_state_directory_creation():
    """Test that save_runtime_state creates state directory if missing."""
    with TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / "nested" / "state"

        # Directory doesn't exist yet
        assert not state_dir.exists()

        # Save should create directory
        state = RuntimeState(updated_at=datetime.now(UTC).isoformat())
        save_runtime_state(state, str(state_dir))

        # Verify directory and file created
        assert state_dir.exists()
        assert (state_dir / "runtime.json").exists()
