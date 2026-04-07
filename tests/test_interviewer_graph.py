from app.agents.interviewer_graph import build_graph, new_state
from app.core.config import settings


def test_graph_generates_first_question_without_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    graph = build_graph()
    state = new_state(
        role="Backend Engineer",
        department="Engineering",
        seniority="mid",
        candidate_name="Jordan",
        skills_required=["Python", "APIs"],
        question_plan=[
            {"id": "q1", "text": "How would you design a resilient API platform?"},
            {"id": "q2", "text": "How do you monitor production incidents?"},
        ],
    )

    result = graph.invoke(state)

    assert result["last_question"] == "How would you design a resilient API platform?"
    assert result["last_question_id"] == "q1"
    assert result["question_index"] == 0


def test_graph_evaluates_answer_and_advances_without_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    graph = build_graph()
    state = new_state(
        role="Backend Engineer",
        department="Engineering",
        seniority="mid",
        candidate_name="Jordan",
        skills_required=["Python", "APIs"],
        question_plan=[
            {"id": "q1", "text": "How would you design a resilient API platform?"},
            {"id": "q2", "text": "How do you monitor production incidents?"},
        ],
    )

    state = graph.invoke(state)
    state["last_answer"] = "I would use rate limiting, retries, observability, and a clear deployment strategy."
    result = graph.invoke(state)

    assert result["last_evaluation"] is not None
    assert result["question_index"] == 1
    assert result["last_question_id"] == "q2"


def test_graph_localizes_question_to_spanish_without_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    graph = build_graph()
    state = new_state(
        role="Backend Engineer",
        department="Engineering",
        seniority="mid",
        candidate_name="Jordan",
        skills_required=["Python", "APIs"],
        question_plan=[
            {"id": "q1", "text": "How would you design a resilient API platform?"},
        ],
        language="es",
    )

    result = graph.invoke(state)

    assert result["last_question_id"] == "q1"
    assert result["last_question"] != "How would you design a resilient API platform?"
    assert "¿Como" in result["last_question"] or "¿Cómo" in result["last_question"]
