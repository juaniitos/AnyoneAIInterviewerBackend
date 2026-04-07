from __future__ import annotations

from app import models
from app.db.session import SessionLocal
from app.services.semantic_questions import ensure_question_embedding


SEED_ROLES = [
    {
        "name": "Senior Neural Architect",
        "description": "Lead the design of multimodal AI systems, retrieval flows, and robust interview agents for premium hiring experiences.",
        "seniority": "senior",
        "department": "Design & Engineering",
        "skills_required": ["Python", "LLMs", "System design", "Vector databases", "Next.js"],
        "questions": [
            ("How would you design a production-ready AI interviewer that can reason about candidate answers turn by turn?", "technical", "hard"),
            ("Describe a time you balanced model quality, latency, and infrastructure cost in an AI product.", "behavioral", "medium"),
            ("What architecture would you use to combine STT, TTS, retrieval, and evaluation in one interview pipeline?", "technical", "hard"),
            ("How do you validate that an LLM-based workflow remains reliable under edge cases and noisy inputs?", "technical", "medium"),
            ("Tell me about a system you built where observability changed an important engineering decision.", "behavioral", "medium"),
        ],
    },
    {
        "name": "Lead Product Strategist",
        "description": "Drive product direction for AI-native workflows, aligning research, design, and engineering around measurable user value.",
        "seniority": "lead",
        "department": "Product",
        "skills_required": ["Product strategy", "Experimentation", "AI UX", "Roadmapping"],
        "questions": [
            ("How do you evaluate whether an AI feature is actually improving the hiring workflow?", "behavioral", "medium"),
            ("Describe a product decision where user research conflicted with stakeholder intuition. What did you do?", "behavioral", "medium"),
            ("How would you prioritize transparency, speed, and automation in an AI interviewer product?", "technical", "medium"),
            ("Tell me about a metric framework you used to judge product quality beyond vanity metrics.", "behavioral", "medium"),
            ("How do you collaborate with engineering to de-risk a new AI capability before launch?", "behavioral", "medium"),
        ],
    },
    {
        "name": "Principal Data Curator",
        "description": "Define the data quality, privacy, and governance strategy behind the AI interviewer platform.",
        "seniority": "principal",
        "department": "Data & Ethics",
        "skills_required": ["Data governance", "Privacy", "NLP datasets", "Evaluation"],
        "questions": [
            ("How would you audit training or evaluation data for bias in an AI-based interview system?", "technical", "hard"),
            ("Tell me about a time you had to trade off data quality against delivery pressure.", "behavioral", "medium"),
            ("What privacy controls would you require before storing candidate transcripts and audio?", "technical", "hard"),
            ("How do you define dataset health for a multilingual speech and text pipeline?", "technical", "medium"),
            ("Describe how you would build trust with recruiters using AI-generated scores.", "behavioral", "medium"),
        ],
    },
]


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        if db.query(models.JobRole).count() > 0:
            return

        for role_data in SEED_ROLES:
            role = models.JobRole(
                name=role_data["name"],
                description=role_data["description"],
                seniority=role_data["seniority"],
                department=role_data["department"],
                skills_required=role_data["skills_required"],
            )
            db.add(role)
            db.flush()

            template = models.InterviewTemplate(
                job_role_id=role.id,
                name=f"{role.name} Core Interview",
                question_count=len(role_data["questions"]),
                max_time_per_question_sec=180,
                system_prompt=(
                    "You are a structured AI interviewer. Ask one question at a time, keep the tone warm and professional, "
                    "and push for concrete examples when answers are vague."
                ),
                evaluation_criteria="Communication, relevance, technical depth, and clarity of examples.",
            )
            db.add(template)

            for text, category, difficulty in role_data["questions"]:
                question = models.Question(
                    job_role_id=role.id,
                    text=text,
                    category=category,
                    difficulty=difficulty,
                    is_active=True,
                )
                ensure_question_embedding(question, role)
                db.add(question)

        db.commit()
    finally:
        db.close()
