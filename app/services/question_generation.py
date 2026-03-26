from app.core.config import settings


def generate_questions(custom_role: str, skills: str | None) -> list[str]:
    base = [
        f"Tell me about your experience related to {custom_role}.",
        f"What is the most challenging problem you have solved as a {custom_role}?",
        f"Describe a project where you used skills relevant to {custom_role}.",
        "How do you prioritize tasks when you have multiple deadlines?",
        "Tell me about a time you received critical feedback and how you handled it.",
    ]
    if skills:
        base.insert(1, f"How have you applied these skills: {skills}?")

    return base[: settings.default_question_count]
