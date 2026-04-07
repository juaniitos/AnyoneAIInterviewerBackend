from app.services.intent_classifier import normalize_intent


def test_normalize_intent_maps_pass_and_idk_to_skip():
    assert normalize_intent("pass") == "skip"
    assert normalize_intent("idk") == "skip"


def test_normalize_intent_detects_clarify_from_utterance():
    assert normalize_intent("", "Can you explain the question?") == "clarify"


def test_normalize_intent_defaults_to_answer():
    assert normalize_intent("", "I designed a distributed caching layer.") == "answer"
