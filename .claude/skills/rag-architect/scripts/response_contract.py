"""Reference RAG answer-outcome and runtime citation validation (rag-response-contract.md §3, §10).

Implements citation validation, the grounding check and the answer-outcome enum (G6, G17), stdlib only:

1. ``decide_retrieval_outcome`` - abstention outcomes decided from the authorized retrieval set,
   before generation: NOT_FOUND, STALE, CONFLICTED, HUMAN_REVIEW (or None = generate).
2. ``validate_answer`` - after generation: membership (every cited chunk is in the packed,
   authorized context), per-claim support, strip unsupported claims, degrade visibly when the
   support checker is unavailable.

Statuses are serialized exactly as rag-response-contract.md §3 spells them (upper case); any other spelling is
rejected at construction. The support checker is injected: production wires an NLI model, an LLM
judge or a managed grounding API; tests use a scripted fake (no network).

Tests: python3 test_response_contract.py   (stdlib unittest; also collected by pytest)
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace

logger = logging.getLogger("rag.response_contract")

ANSWER_OUTCOMES = ("ANSWERED", "PARTIAL", "NOT_FOUND", "CONFLICTED", "STALE", "HUMAN_REVIEW")
OPERATIONAL_STATUSES = ("CLARIFICATION_NEEDED", "TOOL_ERROR", "POLICY_BLOCKED", "NO_RETRIEVAL")
STATUSES = frozenset(ANSWER_OUTCOMES + OPERATIONAL_STATUSES)
ABSTAIN_STATUSES = frozenset({"NOT_FOUND", "CONFLICTED", "STALE", "HUMAN_REVIEW"})

# ADAPT grounding defaults (rag-response-contract.md §10); ratify with evals.
GROUNDING_THRESHOLD = 0.7
GROUNDING_THRESHOLD_HIGH_STAKES = 0.85
CANNOT_CONFIRM = "Cannot confirm from the available sources."


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk of the packed context. Only chunks the caller is authorized for may be passed in."""

    chunk_id: str
    text: str
    doc_id: str
    doc_version: int
    is_current: bool = True      # not superseded (versioning-and-freshness.md)
    is_fresh: bool = True        # inside the corpus freshness window


@dataclass(frozen=True)
class Claim:
    text: str
    chunk_ids: tuple[str, ...]   # citations for this claim


@dataclass(frozen=True)
class Answer:
    status: str
    claims: tuple[Claim, ...] = ()
    verified: bool = True
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in STATUSES:   # exact spelling, no case folding (§3)
            raise ValueError(f"unknown status {self.status!r}; expected one of {sorted(STATUSES)}")

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.claims)

    @property
    def cited_ids(self) -> tuple[str, ...]:
        return tuple(cid for c in self.claims for cid in c.chunk_ids)


# Returns the entailment score of the claim by its cited chunk texts, or None when unavailable.
SupportCheck = Callable[[str, Sequence[str]], Awaitable[float | None]]


def abstention(status: str, reason: str) -> Answer:
    if status not in ABSTAIN_STATUSES:
        raise ValueError(f"{status!r} is not an abstention outcome")
    return Answer(status=status, limitations=(reason,))


def decide_retrieval_outcome(chunks: Sequence[RetrievedChunk], *, high_stakes: bool,
                             retrieval_confidence: float, min_confidence: float) -> Answer | None:
    """Abstention outcomes decided from the authorized retrieval set; None means generate."""
    if not chunks:
        return abstention("NOT_FOUND", "no relevant authorized sources")
    usable = [c for c in chunks if c.is_current and c.is_fresh]
    if not usable:
        return abstention("STALE", "only superseded or past-freshness sources were found")
    versions: dict[str, set[int]] = {}
    for c in usable:
        versions.setdefault(c.doc_id, set()).add(c.doc_version)
    conflicted = sorted(doc for doc, v in versions.items() if len(v) > 1)
    if conflicted:
        return abstention("CONFLICTED", f"sources disagree: {len(conflicted)} document(s) with two current versions")
    if high_stakes and retrieval_confidence < min_confidence:
        return abstention("HUMAN_REVIEW", "high-stakes question with low retrieval confidence")
    return None


async def validate_answer(answer: Answer, chunks_by_id: Mapping[str, str], support_check: SupportCheck,
                          *, high_stakes: bool = False) -> Answer:
    """Runtime citation validation (§10). ``chunks_by_id`` is the packed context the caller is authorized for."""
    if answer.status in ABSTAIN_STATUSES:                   # the four abstention outcomes pass through
        return answer
    fallback = "HUMAN_REVIEW" if high_stakes else "NOT_FOUND"
    if not answer.claims or any(not c.chunk_ids for c in answer.claims):
        return abstention(fallback, "ungrounded: a claim has no citation")
    ghosts = sorted({cid for cid in answer.cited_ids if cid not in chunks_by_id})
    if ghosts:
        logger.warning("citation outside retrieved set", extra={"ghost_chunk_ids": ghosts})  # ids only, no text
        return abstention(fallback, "cited a source that was not retrieved")
    threshold = GROUNDING_THRESHOLD_HIGH_STAKES if high_stakes else GROUNDING_THRESHOLD
    kept: list[Claim] = []
    for claim in answer.claims:
        score = await support_check(claim.text, [chunks_by_id[cid] for cid in claim.chunk_ids])
        if score is None:                                   # checker down: citation-only, labelled unverified
            logger.warning("grounding checker unavailable; answer shipped unverified")
            return replace(answer, verified=False)
        if score >= threshold:
            kept.append(claim)
    if not kept:
        return abstention(fallback, "no claim is supported by its cited source")
    if len(kept) < len(answer.claims):                      # strip unsupported claims (§13.1)
        return replace(answer, status="PARTIAL", claims=tuple(kept),
                       limitations=(*answer.limitations, CANNOT_CONFIRM))
    return answer
