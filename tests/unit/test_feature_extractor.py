"""Unit tests for deterministic feature extraction."""

from app.domain.entities import ChatMessage
from app.domain.features import extract_features


def test_extract_code_feature():
    messages = [
        ChatMessage(role="user", content="Here is my code:\ndef solve(n):\n    return n * 2")
    ]
    features = extract_features(messages)
    assert features.has_code is True
    assert features.is_debugging is False


def test_extract_debugging_feature():
    messages = [
        ChatMessage(role="user", content="I got an exception and traceback: ZeroDivisionError. Help fix this bug.")
    ]
    features = extract_features(messages)
    assert features.is_debugging is True


def test_extract_multistep_feature():
    messages = [
        ChatMessage(role="user", content="Step 1: parse input. Step 2: compute total. Finally format.")
    ]
    features = extract_features(messages)
    assert features.is_multistep is True


def test_extract_simple_routine_feature():
    messages = [
        ChatMessage(role="user", content="What is the capital of Japan?")
    ]
    features = extract_features(messages)
    assert features.has_code is False
    assert features.is_debugging is False
    assert features.is_multistep is False
    assert features.char_length > 0
    assert features.estimated_tokens > 0
