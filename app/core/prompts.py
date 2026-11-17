"""Gateway system prompts, identity definitions, and output sanitizers."""

import re

GATEWAY_SYSTEM_PROMPT = (
    "You are Smart AI Gateway Assistant, an intelligent, helpful, and concise AI assistant built on the Smart AI Gateway platform. "
    "When asked for your name or who you are, state that you are the Smart AI Gateway Assistant. "
    "Never identify yourself as ChatGPT or state that you were created by OpenAI. "
    "Provide clear, direct, and well-structured answers without outputting internal policy thoughts, chain-of-thought traces, or scratchpad notes."
)


def sanitize_llm_response(text: str) -> str:
    """Removes internal chain-of-thought, thinking tags, and policy leakage from model output."""
    if not text:
        return ""
    cleaned = text
    # 1. Remove <think>...</think> tags if present
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()

    # 2. Remove policy reasoning leakage e.g. 'The user asks "..." ... According to policy ... Provide name.'
    policy_patterns = [
        r'The user asks[\s\S]*?Provide name[\.\?!]?',
        r'The user asks[\s\S]*?According to policy[\s\S]*?Provide name[\.\?!]?',
        r'According to policy,[\s\S]*?Provide name[\.\?!]?',
        r'The assistant is ChatGPT[\.\?!]?',
    ]
    for pat in policy_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # 3. Clean any residual ChatGPT claims
    cleaned = re.sub(
        r"I['’]m ChatGPT,\s*an AI language model created by OpenAI[\.\?!]?",
        "I'm the Smart AI Gateway Assistant.",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"I am ChatGPT,\s*a large language model trained by OpenAI[\.\?!]?",
        "I am the Smart AI Gateway Assistant.",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()
