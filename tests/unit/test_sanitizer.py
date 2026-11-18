from app.core.prompts import sanitize_llm_response


def test_sanitize_policy_leakage_and_chatgpt_claims():
    raw = (
        'The user asks "what is your name?" They repeated. We need to answer. '
        "According to policy, we can give name. The assistant is ChatGPT. Provide name."
        "I’m ChatGPT, an AI language model created by OpenAI. How can I help you today?"
    )
    cleaned = sanitize_llm_response(raw)
    assert "The user asks" not in cleaned
    assert "According to policy" not in cleaned
    assert "OpenAI" not in cleaned
    assert "ChatGPT" not in cleaned
    assert "Smart AI Gateway" in cleaned


def test_sanitize_think_tags():
    raw = "<think>Internal reasoning trace</think>Here is the final answer."
    cleaned = sanitize_llm_response(raw)
    assert cleaned == "Here is the final answer."
