"""Tests for mock LLM provider."""

from tests.mocks.mock_llm_provider import MockLLMProvider


def test_mock_provider_default_response():
    """Test mock provider returns default response."""
    provider = MockLLMProvider("test")

    response = provider.generate_structured_json("test prompt", {})

    assert "proposals" in response
    assert len(response["proposals"]) == 1
    assert response["proposals"][0]["sector_name"] == "mega_cap_tech"
    assert provider.call_count == 1
    assert provider.get_provider_name() == "test"


def test_mock_provider_custom_response():
    """Test mock provider with custom response."""
    custom_response = {
        "proposals": [
            {
                "sector_name": "custom_sector",
                "recommended_enabled": False,
                "confidence": 0.75,
                "rationale": "Custom rationale",
                "supporting_headline_numbers": [1, 2, 3],
            }
        ]
    }

    provider = MockLLMProvider("custom", custom_response)
    response = provider.generate_structured_json("prompt", {})

    assert response == custom_response
    assert provider.call_count == 1


def test_mock_provider_call_history():
    """Test mock provider records call history."""
    provider = MockLLMProvider("test")

    provider.generate_structured_json(
        "prompt1", {"schema": "test"}, temperature=0.5, max_tokens=1000
    )
    provider.generate_structured_json(
        "prompt2", {"schema": "test2"}, temperature=0.8, max_tokens=2000
    )

    assert provider.call_count == 2
    assert len(provider.call_history) == 2
    assert provider.call_history[0]["prompt"] == "prompt1"
    assert provider.call_history[0]["temperature"] == 0.5
    assert provider.call_history[1]["prompt"] == "prompt2"
    assert provider.call_history[1]["max_tokens"] == 2000
