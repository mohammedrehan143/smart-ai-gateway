"""Advanced Two-Tier Cache (Exact SHA-256 + Context-Safe Semantic Similarity) with tenant isolation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from app.core.logging import get_logger
from app.domain.entities import ChatMessage, GenerationParameters, NormalizedCompletion

logger = get_logger("semantic_cache")


@dataclass
class SemanticCacheEntry:
    cache_key: str
    tenant_id: str
    model_alias: str
    normalized_prompt: str
    prompt_tokens_set: Set[str]
    vector_magnitude: float
    completion: NormalizedCompletion
    expires_at: float
    created_at: float = field(default_factory=time.time)


class AdvancedSemanticCache:
    """Two-tier response cache supporting exact matching, semantic similarity, and tenant isolation."""

    def __init__(self, default_ttl_seconds: int = 300, similarity_threshold: float = 0.95):
        self.default_ttl = default_ttl_seconds
        self.similarity_threshold = similarity_threshold
        # Exact cache: Dict[exact_key, (completion, expires_at)]
        self._exact_cache: Dict[str, Tuple[NormalizedCompletion, float]] = {}
        # Semantic cache: List[SemanticCacheEntry]
        self._semantic_entries: List[SemanticCacheEntry] = []
        self.exact_hits: int = 0
        self.semantic_hits: int = 0
        self.misses: int = 0

    def compute_exact_key(
        self,
        tenant_id: str,
        model_alias: str,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
    ) -> str:
        """Deterministic SHA-256 cache key including tenant isolation and model identity."""
        normalized = [{"role": m.role, "content": m.content.strip()} for m in messages]
        payload = {
            "tenant_id": tenant_id,
            "model": model_alias,
            "messages": normalized,
            "temperature": parameters.temperature,
            "max_output_tokens": parameters.max_output_tokens,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip())

    def _tokenize_vector(self, text: str) -> Counter:
        words = re.findall(r"\w+", self._normalize_text(text))
        return Counter(words)

    def _cosine_similarity(self, vec1: Counter, vec2: Counter) -> float:
        intersection = set(vec1.keys()) & set(vec2.keys())
        numerator = sum(vec1[x] * vec2[x] for x in intersection)

        sum1 = sum(x**2 for x in vec1.values())
        sum2 = sum(x**2 for x in vec2.values())
        denominator = math.sqrt(sum1) * math.sqrt(sum2)

        if not denominator:
            return 0.0
        return float(numerator) / denominator

    def _has_differing_critical_qualifiers(self, text1: str, text2: str) -> bool:
        """Context-safety invariant: if negative qualifiers, entity numbers, or directives differ, reject match."""
        negatives = {"not", "no", "never", "neither", "nor", "without", "except"}
        words1 = set(re.findall(r"\w+", text1.lower()))
        words2 = set(re.findall(r"\w+", text2.lower()))

        # Check differing negative qualifiers
        if words1.intersection(negatives) != words2.intersection(negatives):
            return True

        # Check differing numbers/quantities
        nums1 = set(re.findall(r"\b\d+\b", text1))
        nums2 = set(re.findall(r"\b\d+\b", text2))
        if nums1 != nums2:
            return True

        return False

    async def get(
        self,
        tenant_id: str,
        model_alias: str,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
    ) -> Tuple[Optional[NormalizedCompletion], str]:
        """Looks up cache across L1 Exact match, then L2 Context-Safe Semantic match.

        Returns (Completion, Cache Status: 'hit_exact', 'hit_semantic', or 'miss').
        """
        now = time.time()
        # 1. L1 Exact Match
        exact_key = self.compute_exact_key(tenant_id, model_alias, messages, parameters)
        if exact_key in self._exact_cache:
            comp, expires_at = self._exact_cache[exact_key]
            if now < expires_at:
                self.exact_hits += 1
                return comp, "hit_exact"
            else:
                del self._exact_cache[exact_key]

        # 2. L2 Semantic Match (Only for deterministic temperature <= 0.2)
        if parameters.temperature > 0.2:
            self.misses += 1
            return None, "miss"

        user_text = " ".join(m.content for m in messages if m.role == "user")
        normalized_query = self._normalize_text(user_text)
        query_vec = self._tokenize_vector(normalized_query)

        for entry in self._semantic_entries:
            if entry.tenant_id != tenant_id or entry.model_alias != model_alias:
                continue
            if now > entry.expires_at:
                continue

            # Context Invariant Check
            if self._has_differing_critical_qualifiers(normalized_query, entry.normalized_prompt):
                continue

            entry_vec = self._tokenize_vector(entry.normalized_prompt)
            sim = self._cosine_similarity(query_vec, entry_vec)

            if sim >= self.similarity_threshold:
                self.semantic_hits += 1
                logger.info(f"Semantic cache hit (sim={sim:.3f}) for tenant '{tenant_id}' on model '{model_alias}'")
                return entry.completion, "hit_semantic"

        self.misses += 1
        return None, "miss"

    async def set(
        self,
        tenant_id: str,
        model_alias: str,
        messages: List[ChatMessage],
        parameters: GenerationParameters,
        completion: NormalizedCompletion,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = time.time() + ttl

        # Set L1 Exact
        exact_key = self.compute_exact_key(tenant_id, model_alias, messages, parameters)
        self._exact_cache[exact_key] = (completion, expires_at)

        # Set L2 Semantic (Only if deterministic)
        if parameters.temperature <= 0.2:
            user_text = " ".join(m.content for m in messages if m.role == "user")
            norm_prompt = self._normalize_text(user_text)
            words = set(re.findall(r"\w+", norm_prompt))

            self._semantic_entries.append(
                SemanticCacheEntry(
                    cache_key=exact_key,
                    tenant_id=tenant_id,
                    model_alias=model_alias,
                    normalized_prompt=norm_prompt,
                    prompt_tokens_set=words,
                    vector_magnitude=float(len(words)),
                    completion=completion,
                    expires_at=expires_at,
                )
            )

    def invalidate_tenant(self, tenant_id: str) -> int:
        """Invalidates all cached entries belonging to a specific tenant."""
        initial_count = len(self._semantic_entries)
        self._semantic_entries = [e for e in self._semantic_entries if e.tenant_id != tenant_id]
        # Invalidate exact cache entries for tenant
        exact_to_del = [k for k in self._exact_cache if k.startswith(tenant_id)]
        for k in exact_to_del:
            del self._exact_cache[k]
        return initial_count - len(self._semantic_entries)

    def clear(self) -> None:
        self._exact_cache.clear()
        self._semantic_entries.clear()
        self.exact_hits = 0
        self.semantic_hits = 0
        self.misses = 0


default_semantic_cache = AdvancedSemanticCache()
