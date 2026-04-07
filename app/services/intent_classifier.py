from __future__ import annotations


CLARIFY_MARKERS = {
    "clarify",
    "can you explain",
    "what do you mean",
    "repeat",
    "rephrase",
    "i don't understand",
    "could you explain",
}

SKIP_MARKERS = {
    "skip",
    "pass",
    "idk",
    "i don't know",
    "no idea",
}


def normalize_intent(intent: str, utterance: str | None = None) -> str:
    lowered_intent = (intent or "").strip().lower()
    lowered_utterance = (utterance or "").strip().lower()

    if lowered_intent in {"clarify", "skip", "pass", "idk", "answer"}:
        if lowered_intent in {"pass", "idk"}:
            return "skip"
        return lowered_intent

    if any(marker in lowered_utterance for marker in CLARIFY_MARKERS):
        return "clarify"
    if any(marker in lowered_utterance for marker in SKIP_MARKERS):
        return "skip"
    return "answer"
