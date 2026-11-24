"""Contract tests for response_contract.py (rag-response-contract.md §3, §10).

Stdlib unittest with a scripted support checker: no network, no model. Run from anywhere:
    python3 .claude/skills/rag-architect/scripts/test_response_contract.py
(pytest also collects it.) Each test names the register row it evidences.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from response_contract import (  # sibling module; path set above
    ABSTAIN_STATUSES, ANSWER_OUTCOMES, CANNOT_CONFIRM, Answer, Claim, RetrievedChunk,
    decide_retrieval_outcome, validate_answer,
)

CHUNKS = {"c1": "Refunds are issued within 14 days.", "c2": "Refunds require a receipt."}


class ScriptedChecker:
    """Fake support checker: returns a fixed score per claim text; records every call."""

    def __init__(self, scores):
        self.scores, self.calls = scores, []

    async def __call__(self, claim, chunk_texts):
        self.calls.append((claim, tuple(chunk_texts)))
        return self.scores[claim]


def chunk(cid, doc="policy", version=1, current=True, fresh=True):
    return RetrievedChunk(cid, CHUNKS.get(cid, "text"), doc, version, current, fresh)


def decide(chunks, high_stakes=False, confidence=0.9):
    return decide_retrieval_outcome(chunks, high_stakes=high_stakes, retrieval_confidence=confidence,
                                    min_confidence=0.6)


GROUNDED = Answer("ANSWERED", (Claim("Refunds take 14 days.", ("c1",)), Claim("A receipt is needed.", ("c2",))))


class AnswerOutcomes(unittest.IsolatedAsyncioTestCase):
    async def test_answered_grounded_cited_above_threshold(self):  # RAG-13.3-01
        self.assertIsNone(decide([chunk("c1"), chunk("c2")]))
        checker = ScriptedChecker({"Refunds take 14 days.": 0.92, "A receipt is needed.": 0.88})
        out = await validate_answer(GROUNDED, CHUNKS, checker)
        self.assertEqual(out.status, "ANSWERED")
        self.assertTrue(out.verified)
        self.assertEqual(out.cited_ids, ("c1", "c2"))
        self.assertEqual(out.text, "Refunds take 14 days. A receipt is needed.")
        self.assertEqual(checker.calls, [("Refunds take 14 days.", (CHUNKS["c1"],)),
                                         ("A receipt is needed.", (CHUNKS["c2"],))])

    def test_not_found_when_no_authorized_chunks(self):  # RAG-13.3-03
        self.assertEqual(decide([]).status, "NOT_FOUND")

    def test_conflicted_when_two_current_versions_disagree(self):  # RAG-13.3-04
        out = decide([chunk("c1", version=3), chunk("c2", version=4)])
        self.assertEqual(out.status, "CONFLICTED")
        self.assertFalse(out.claims)                     # never picks one version silently

    def test_stale_when_only_superseded_or_expired_sources(self):  # RAG-13.3-05
        self.assertEqual(decide([chunk("c1", current=False), chunk("c2", fresh=False)]).status, "STALE")
        # one usable fresh source is not STALE (stale_source flag territory instead)
        self.assertIsNone(decide([chunk("c1", current=False), chunk("c2")]))

    async def test_human_review_high_stakes_low_confidence(self):  # RAG-13.3-06
        self.assertEqual(decide([chunk("c1")], high_stakes=True, confidence=0.4).status, "HUMAN_REVIEW")
        self.assertIsNone(decide([chunk("c1")], high_stakes=False, confidence=0.4))
        # high-stakes grounding threshold is 0.85: 0.8 passes general, escalates high-stakes
        checker = ScriptedChecker({"Refunds take 14 days.": 0.8, "A receipt is needed.": 0.8})
        self.assertEqual((await validate_answer(GROUNDED, CHUNKS, checker)).status, "ANSWERED")
        self.assertEqual((await validate_answer(GROUNDED, CHUNKS, checker, high_stakes=True)).status,
                         "HUMAN_REVIEW")

    async def test_abstentions_pass_through_validation_unchanged(self):
        checker = ScriptedChecker({})
        for status in sorted(ABSTAIN_STATUSES):
            with self.subTest(status=status):
                ans = Answer(status, limitations=("x",))
                self.assertIs(await validate_answer(ans, CHUNKS, checker), ans)
        self.assertEqual(checker.calls, [])


class CitationValidation(unittest.IsolatedAsyncioTestCase):  # RAG-13.1-01
    async def test_ghost_citation_abstains_without_calling_checker(self):
        ans = Answer("ANSWERED", (Claim("Refunds take 14 days.", ("c1", "c9")),))
        checker = ScriptedChecker({})
        out = await validate_answer(ans, CHUNKS, checker)
        self.assertEqual((out.status, out.claims, checker.calls), ("NOT_FOUND", (), []))

    async def test_uncited_claim_abstains(self):
        ans = Answer("ANSWERED", (Claim("Refunds take 14 days.", ("c1",)), Claim("Free shipping.", ())))
        self.assertEqual((await validate_answer(ans, CHUNKS, ScriptedChecker({}))).status, "NOT_FOUND")
        self.assertEqual((await validate_answer(Answer("ANSWERED"), CHUNKS, ScriptedChecker({}))).status,
                         "NOT_FOUND")

    async def test_unsupported_claim_is_stripped(self):
        checker = ScriptedChecker({"Refunds take 14 days.": 0.95, "A receipt is needed.": 0.2})
        out = await validate_answer(GROUNDED, CHUNKS, checker)
        self.assertEqual(out.status, "PARTIAL")
        self.assertEqual(out.text, "Refunds take 14 days.")
        self.assertEqual(out.cited_ids, ("c1",))
        self.assertIn(CANNOT_CONFIRM, out.limitations)

    async def test_no_supported_claim_abstains(self):
        checker = ScriptedChecker({"Refunds take 14 days.": 0.1, "A receipt is needed.": 0.69})
        out = await validate_answer(GROUNDED, CHUNKS, checker)
        self.assertEqual((out.status, out.claims), ("NOT_FOUND", ()))

    async def test_checker_unavailable_ships_unverified(self):
        checker = ScriptedChecker({"Refunds take 14 days.": None, "A receipt is needed.": 0.9})
        out = await validate_answer(GROUNDED, CHUNKS, checker)
        self.assertEqual((out.status, out.verified, out.claims), ("ANSWERED", False, GROUNDED.claims))


class ExactSpelling(unittest.TestCase):
    def test_outcomes_are_upper_case_standard_spelling(self):
        self.assertEqual(ANSWER_OUTCOMES,
                         ("ANSWERED", "PARTIAL", "NOT_FOUND", "CONFLICTED", "STALE", "HUMAN_REVIEW"))
        self.assertEqual(ABSTAIN_STATUSES, {"NOT_FOUND", "CONFLICTED", "STALE", "HUMAN_REVIEW"})

    def test_other_spellings_rejected(self):
        for bad in ("answered", "Answered", "not_found", "NOT-FOUND", "HUMAN REVIEW", "STALE "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Answer(bad)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() and result.testsRun > 0 else 1)
