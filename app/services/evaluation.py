import math


def evaluate_answer(question: str, transcript: str) -> tuple[int, str]:
    word_count = len(transcript.split())
    score = max(1, min(5, math.ceil(word_count / 40)))
    feedback = "Provide more concrete examples." if score <= 2 else "Solid response with relevant details."
    return score, feedback
