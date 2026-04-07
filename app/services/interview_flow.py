from __future__ import annotations

from statistics import mean

from app import models


def score_transcript(question: str, transcript: str) -> tuple[float, str]:
    word_count = len([word for word in transcript.split() if word.strip()])
    question_terms = {term.lower().strip(".,?!") for term in question.split() if len(term) > 4}
    transcript_terms = {term.lower().strip(".,?!") for term in transcript.split()}
    overlap = len(question_terms & transcript_terms)

    score = 3.5
    if word_count >= 25:
        score += 1.0
    if word_count >= 60:
        score += 1.5
    if overlap >= 2:
        score += 1.0
    if overlap >= 4:
        score += 0.5
    if word_count < 10:
        score -= 1.5

    bounded = max(1.0, min(10.0, round(score, 1)))

    if bounded >= 8:
        feedback = "Strong answer with relevant detail and clear alignment to the question."
    elif bounded >= 6:
        feedback = "Good foundation. A bit more precision or concrete examples would strengthen it."
    else:
        feedback = "The answer is brief or generic. Add examples, tradeoffs, and measurable impact."

    return bounded, feedback


def evaluate_session(questions: list[models.Question], answers: list[models.Answer]) -> dict[str, str | float]:
    question_map = {question.id: question for question in questions}
    per_answer_scores: list[float] = []
    strengths: list[str] = []
    improvements: list[str] = []

    for answer in answers:
        question = question_map.get(answer.question_id)
        if not question:
            continue
        score, feedback = score_transcript(question.text, answer.transcript)
        per_answer_scores.append(score)
        if score >= 7.5:
            strengths.append(f"Q{answer.question_number}: {feedback}")
        else:
            improvements.append(f"Q{answer.question_number}: {feedback}")

    final_score = round(mean(per_answer_scores), 1) if per_answer_scores else 1.0

    if final_score >= 8:
        recommendation = "strong_yes"
        summary = "Candidate showed strong communication, relevant examples, and clear technical alignment."
    elif final_score >= 6:
        recommendation = "consider"
        summary = "Candidate demonstrated promising fundamentals, with room to deepen some responses."
    else:
        recommendation = "needs_review"
        summary = "Candidate needs more depth and structure in several responses before moving forward."

    return {
        "score": final_score,
        "summary": summary,
        "strengths": "\n".join(strengths) if strengths else "Candidate maintained a consistent baseline across the interview.",
        "areas_of_improvement": "\n".join(improvements) if improvements else "No major gaps were detected in this pass.",
        "recommendation": recommendation,
        "model_used": "rule-based-evaluator-v1",
    }
