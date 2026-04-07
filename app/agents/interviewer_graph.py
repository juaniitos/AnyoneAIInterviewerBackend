from __future__ import annotations

import re
from statistics import mean
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents.prompts import (
    EVALUATION_HUMAN,
    EVALUATION_SYSTEM,
    FINAL_HUMAN,
    FINAL_SYSTEM,
    QUESTION_HUMAN,
    QUESTION_SYSTEM,
)
from app.core.config import settings

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:  # pragma: no cover
    ChatAnthropic = None  # type: ignore[assignment]


class Evaluation(BaseModel):
    score: float = Field(ge=0, le=10)
    strengths: List[str]
    gaps: List[str]
    follow_up: str
    should_probe: bool = False
    summary: str


class FinalNarrative(BaseModel):
    recommendation: str
    strengths: List[str]
    gaps: List[str]
    summary: str


class InterviewState(TypedDict):
    language: str
    role: str
    department: str
    seniority: str
    candidate_name: str
    skills_required: List[str]
    num_questions: int
    question_index: int
    question_plan: List[Dict[str, str]]
    asked_questions: List[str]
    qa_pairs: List[Dict[str, str]]
    evaluations: List[Dict[str, Any]]
    last_question_id: str
    last_question: str
    last_answer: str
    last_evaluation: Optional[Dict[str, Any]]
    final_report: Optional[Dict[str, Any]]
    is_finished: bool


_llm: Optional[ChatAnthropic] = None

SPANISH_MARKERS = (
    " el ",
    " la ",
    " los ",
    " las ",
    " un ",
    " una ",
    " de ",
    " que ",
    " para ",
    " como ",
    " cual ",
    " cuentame ",
    " describe ",
    " experiencia ",
    " habilidades ",
    " proyecto ",
    " retroalimentacion ",
    " privacidad ",
)
ENGLISH_MARKERS = (
    " the ",
    " a ",
    " an ",
    " about ",
    " related ",
    " describe ",
    " project ",
    " skills ",
    " feedback ",
    " question ",
    " how ",
    " what ",
    " tell me ",
)

SPANISH_PHRASE_REPLACEMENTS = [
    (r"\bhow would you\b", "como"),
    (r"\bwhat privacy controls\b", "que controles de privacidad"),
    (r"\bwhat safeguards\b", "que salvaguardas"),
    (r"\bwhat tradeoffs\b", "que tradeoffs"),
    (r"\bwhat risks\b", "que riesgos"),
    (r"\bwhat\b", "que"),
    (r"\bwould you require\b", "requeririas"),
    (r"\bbefore storing\b", "antes de almacenar"),
    (r"\bbefore shipping\b", "antes de lanzar"),
    (r"\bcandidate transcripts\b", "transcripciones de candidatos"),
    (r"\bcandidate audio\b", "audio de candidatos"),
    (r"\btraining or evaluation data\b", "datos de entrenamiento o evaluacion"),
    (r"\btraining data\b", "datos de entrenamiento"),
    (r"\bevaluation data\b", "datos de evaluacion"),
    (r"\bAI-based interview system\b", "sistema de entrevistas basado en IA"),
    (r"\binterview system\b", "sistema de entrevistas"),
    (r"\bfor bias\b", "para sesgo"),
    (r"\bbias\b", "sesgo"),
    (r"\bprivacy controls\b", "controles de privacidad"),
    (r"\bprivacy\b", "privacidad"),
    (r"\btranscripts\b", "transcripciones"),
    (r"\ban AI-based interview system\b", "un sistema de entrevistas basado en IA"),
    (r"\bin an AI-based interview system\b", "en un sistema de entrevistas basado en IA"),
    (r"\bin an interview system\b", "en un sistema de entrevistas"),
    (r"\bin production\b", "en produccion"),
    (r"\bfor\b", "para"),
    (r"\bin\b", "en"),
    (r"\ban\b", "un"),
    (r"\baudio\b", "audio"),
    (r"\band\b", "y"),
    (r"\bor\b", "o"),
    (r"\bstoring\b", "almacenar"),
    (r"\bmonitor failures in production\b", "monitorear fallas en produccion"),
    (r"\bmonitor\b", "monitorear"),
    (r"\baudit\b", "auditar"),
    (r"\bdesign\b", "disenar"),
    (r"\bresilient\b", "resiliente"),
]
ENGLISH_PHRASE_REPLACEMENTS = [
    (r"\bcomo\b", "how"),
    (r"\bque controles de privacidad\b", "what privacy controls"),
    (r"\bque salvaguardas\b", "what safeguards"),
    (r"\bque riesgos\b", "what risks"),
    (r"\brequeririas\b", "would you require"),
    (r"\bantes de almacenar\b", "before storing"),
    (r"\btranscripciones de candidatos\b", "candidate transcripts"),
    (r"\baudio de candidatos\b", "candidate audio"),
    (r"\bdatos de entrenamiento o evaluacion\b", "training or evaluation data"),
    (r"\bdatos de entrenamiento\b", "training data"),
    (r"\bdatos de evaluacion\b", "evaluation data"),
    (r"\bsistema de entrevistas basado en IA\b", "AI-based interview system"),
    (r"\bsistema de entrevistas\b", "interview system"),
    (r"\bpara sesgo\b", "for bias"),
    (r"\bsesgo\b", "bias"),
    (r"\bcontroles de privacidad\b", "privacy controls"),
    (r"\bprivacidad\b", "privacy"),
    (r"\bun sistema de entrevistas basado en IA\b", "an AI-based interview system"),
    (r"\ben un sistema de entrevistas basado en IA\b", "in an AI-based interview system"),
    (r"\ben un sistema de entrevistas\b", "in an interview system"),
    (r"\ben produccion\b", "in production"),
    (r"\bpara\b", "for"),
    (r"\ben\b", "in"),
    (r"\bun\b", "an"),
    (r"\btranscripciones\b", "transcripts"),
    (r"\by\b", "and"),
    (r"\bo\b", "or"),
    (r"\balmacenar\b", "storing"),
    (r"\bmonitorear\b", "monitor"),
    (r"\bauditar\b", "audit"),
    (r"\bdisenar\b", "design"),
    (r"\bresiliente\b", "resilient"),
]


def normalize_language(language: str | None) -> str:
    value = (language or "en").strip().lower()
    if value.startswith("es"):
        return "es"
    return "en"


def language_label(language: str | None) -> str:
    return "Spanish" if normalize_language(language) == "es" else "English"


def get_llm() -> Optional[ChatAnthropic]:
    global _llm
    if _llm is not None:
        return _llm
    if not settings.anthropic_api_key or ChatAnthropic is None:
        return None
    _llm = ChatAnthropic(
        model=settings.anthropic_model,
        temperature=settings.anthropic_temperature,
        api_key=settings.anthropic_api_key,
        max_retries=2,
    )
    return _llm


def new_state(
    role: str,
    department: str,
    seniority: str,
    candidate_name: str,
    skills_required: List[str],
    question_plan: List[Dict[str, str]],
    language: str = "en",
) -> InterviewState:
    return InterviewState(
        language=normalize_language(language),
        role=role,
        department=department,
        seniority=seniority,
        candidate_name=candidate_name,
        skills_required=skills_required,
        num_questions=len(question_plan),
        question_index=0,
        question_plan=question_plan,
        asked_questions=[],
        qa_pairs=[],
        evaluations=[],
        last_question_id="",
        last_question="",
        last_answer="",
        last_evaluation=None,
        final_report=None,
        is_finished=False,
    )


def _format_recent_context(qa_pairs: List[Dict[str, str]]) -> str:
    if not qa_pairs:
        return "None"
    recent = qa_pairs[-settings.max_context_qa :]
    return "\n".join(
        [
            f"Q{idx + 1}: {item['question']}\nA{idx + 1}: {item['answer']}"
            for idx, item in enumerate(recent)
        ]
    )


def _normalize_for_detection(text: str) -> str:
    normalized = f" {text.lower()} "
    normalized = normalized.replace("á", "a").replace("é", "e").replace("í", "i")
    normalized = normalized.replace("ó", "o").replace("ú", "u")
    normalized = normalized.replace("¿", " ").replace("¡", " ").replace("ñ", "n")
    return normalized


def _looks_spanish(text: str) -> bool:
    normalized = _normalize_for_detection(text)
    if any(char in text for char in ("¿", "¡", "ñ", "á", "é", "í", "ó", "ú")):
        return True
    return sum(marker in normalized for marker in SPANISH_MARKERS) >= 2


def _needs_localization(text: str, language: str) -> bool:
    target_language = normalize_language(language)
    if not text.strip():
        return False
    if target_language == "es":
        return not _looks_spanish(text)
    return _looks_spanish(text)


def _phrase_based_question_translation(text: str, language: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    replacements = (
        SPANISH_PHRASE_REPLACEMENTS
        if normalize_language(language) == "es"
        else ENGLISH_PHRASE_REPLACEMENTS
    )

    translated = cleaned.lower()
    for pattern, replacement in replacements:
        translated = re.sub(pattern, replacement, translated, flags=re.IGNORECASE)

    translated = re.sub(r"\s+", " ", translated).strip(" ?.!")
    if translated == cleaned.lower():
        return cleaned

    first_alpha = next((idx for idx, char in enumerate(translated) if char.isalpha()), None)
    if first_alpha is not None:
        translated = translated[:first_alpha] + translated[first_alpha].upper() + translated[first_alpha + 1 :]
    if normalize_language(language) == "es":
        if not translated.startswith("¿"):
            translated = f"¿{translated}"
        if not translated.endswith("?"):
            translated = f"{translated}?"
    else:
        translated = translated.lstrip("¿")
        if not translated.endswith("?"):
            translated = f"{translated}?"
    return translated


def _rule_based_question_translation(text: str, language: str) -> str:
    normalized_language = normalize_language(language)
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    if normalized_language == "es":
        patterns = [
            (r"^Tell me about your experience related to (.+?)\.?$", r"Cuentame sobre tu experiencia relacionada con \1."),
            (r"^What is the most challenging problem you have solved as a[n]? (.+?)\?$", r"¿Cual es el problema mas desafiante que has resuelto como \1?"),
            (r"^Describe a project where you used skills relevant to (.+?)\.?$", r"Describe un proyecto en el que hayas usado habilidades relevantes para \1."),
            (r"^How have you applied these skills: (.+?)\?$", r"¿Como has aplicado estas habilidades: \1?"),
            (r"^How do you prioritize tasks when you have multiple deadlines\?$", r"¿Como priorizas tareas cuando tienes multiples fechas limite?"),
            (r"^Tell me about a time you received critical feedback and how you handled it\.?$", r"Cuentame sobre una ocasion en la que recibiste retroalimentacion critica y como la manejaste."),
            (r"^How would you design a resilient (.+?)\?$", r"¿Como disenarias un(a) \1 resiliente?"),
            (r"^How would you monitor (.+?)\?$", r"¿Como monitorearias \1?"),
            (r"^How would you audit (.+?)\?$", r"¿Como auditarias \1?"),
        ]
    else:
        patterns = [
            (r"^Cuentame sobre tu experiencia relacionada con (.+?)\.?$", r"Tell me about your experience related to \1."),
            (r"^¿?Cual es el problema mas desafiante que has resuelto como (.+?)\??$", r"What is the most challenging problem you have solved as a \1?"),
            (r"^Describe un proyecto en el que hayas usado habilidades relevantes para (.+?)\.?$", r"Describe a project where you used skills relevant to \1."),
            (r"^¿?Como has aplicado estas habilidades: (.+?)\??$", r"How have you applied these skills: \1?"),
            (r"^¿?Como priorizas tareas cuando tienes multiples fechas limite\??$", r"How do you prioritize tasks when you have multiple deadlines?"),
            (r"^Cuentame sobre una ocasion en la que recibiste retroalimentacion critica y como la manejaste\.?$", r"Tell me about a time you received critical feedback and how you handled it."),
            (r"^¿?Como disenarias un\(a\) (.+?) resiliente\??$", r"How would you design a resilient \1?"),
            (r"^¿?Como monitorearias (.+?)\??$", r"How would you monitor \1?"),
            (r"^¿?Como auditarias (.+?)\??$", r"How would you audit \1?"),
        ]

    for pattern, replacement in patterns:
        translated = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if translated != cleaned:
            return _phrase_based_question_translation(translated, normalized_language)

    return _phrase_based_question_translation(cleaned, normalized_language)


def ensure_question_language(text: str, language: str, llm: Optional[ChatAnthropic] = None) -> str:
    target_language = normalize_language(language)
    if not _needs_localization(text, target_language):
        return text.strip()

    translator = llm or get_llm()
    if translator is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Translate the interview question into {language_label}. Preserve meaning, tone, and specificity. Return only the translated question.",
                ),
                ("human", "Question:\n{question}"),
            ]
        )
        messages = prompt.format_messages(
            language_label=language_label(target_language),
            question=text,
        )
        try:
            translated = str(translator.invoke(messages).content).strip()
            if translated and not _needs_localization(translated, target_language):
                return translated
        except Exception:
            pass

    fallback = _rule_based_question_translation(text, target_language)
    return fallback.strip() or text.strip()


def _fallback_question(state: InterviewState) -> str:
    question = state["question_plan"][state["question_index"]]
    return ensure_question_language(question["text"], state["language"])


def _fallback_evaluation(question: str, answer: str, language: str) -> Dict[str, Any]:
    word_count = len([word for word in answer.split() if word.strip()])
    score = 4.5
    if word_count >= 20:
        score += 1.5
    if word_count >= 45:
        score += 1.5
    if word_count < 8:
        score -= 2.0
    bounded = max(1.0, min(10.0, round(score, 1)))
    is_spanish = normalize_language(language) == "es"
    return {
        "score": bounded,
        "strengths": (
            ["La respuesta se mantiene en el tema."]
            if is_spanish and bounded >= 6
            else ["Answer stays on topic."] if bounded >= 6 else []
        ),
        "gaps": (
            ["Necesita ejemplos mas concretos y mayor profundidad."]
            if is_spanish and bounded < 7
            else ["Needs more concrete examples and stronger depth."] if bounded < 7 else []
        ),
        "follow_up": (
            f"Puedes dar un ejemplo mas concreto relacionado con: {question}"
            if is_spanish
            else f"Can you give a more concrete example related to: {question}"
        ),
        "should_probe": bounded < 7,
        "summary": (
            "Va bien encaminada, pero la respuesta necesita mas especificidad."
            if is_spanish and bounded < 7
            else "Respuesta solida con detalles relevantes."
            if is_spanish
            else "Good direction, but the answer would benefit from more specificity."
            if bounded < 7
            else "Solid answer with relevant detail."
        ),
    }


def generate_question(state: InterviewState) -> Dict[str, Any]:
    if state["is_finished"] or state["question_index"] >= state["num_questions"]:
        return {}

    planned_question = state["question_plan"][state["question_index"]]
    llm = get_llm()
    question_text = planned_question["text"]

    if llm is not None:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", QUESTION_SYSTEM),
                ("human", QUESTION_HUMAN),
            ]
        )
        messages = prompt.format_messages(
            language_label=language_label(state["language"]),
            candidate_name=state["candidate_name"],
            role=state["role"],
            department=state["department"],
            seniority=state["seniority"],
            skills_required=", ".join(state["skills_required"]) or "general fundamentals",
            recent_context=_format_recent_context(state["qa_pairs"]),
            planned_question=planned_question["text"],
        )
        question_text = str(llm.invoke(messages).content).strip() or question_text

    question_text = ensure_question_language(question_text, state["language"], llm=llm)

    return {
        "last_question_id": planned_question["id"],
        "last_question": question_text,
        "asked_questions": state["asked_questions"] + [question_text],
    }


def evaluate_answer(state: InterviewState) -> Dict[str, Any]:
    if not state["last_answer"].strip():
        return {}

    llm = get_llm()
    evaluation_dict: Dict[str, Any]

    if llm is not None:
        evaluator = llm.with_structured_output(Evaluation)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EVALUATION_SYSTEM),
                ("human", EVALUATION_HUMAN),
            ]
        )
        messages = prompt.format_messages(
            language_label=language_label(state["language"]),
            candidate_name=state["candidate_name"],
            role=state["role"],
            department=state["department"],
            seniority=state["seniority"],
            question=state["last_question"],
            answer=state["last_answer"],
        )
        evaluation = evaluator.invoke(messages)
        evaluation_dict = evaluation.model_dump()
    else:
        evaluation_dict = _fallback_evaluation(state["last_question"], state["last_answer"], state["language"])

    qa_pairs = state["qa_pairs"] + [
        {
            "question_id": state["last_question_id"],
            "question": state["last_question"],
            "answer": state["last_answer"],
        }
    ]
    evaluations = state["evaluations"] + [evaluation_dict]

    return {
        "qa_pairs": qa_pairs,
        "evaluations": evaluations,
        "last_answer": "",
        "last_evaluation": evaluation_dict,
        "question_index": state["question_index"] + 1,
    }


def finalize(state: InterviewState) -> Dict[str, Any]:
    if not state["evaluations"]:
        return {"is_finished": True, "final_report": None}

    scores = [float(item["score"]) for item in state["evaluations"] if "score" in item]
    overall_score = round(mean(scores), 1) if scores else 1.0

    llm = get_llm()
    if llm is not None:
        narrator = llm.with_structured_output(FinalNarrative)
        evaluations_text = "\n".join(
            [
                f"- Q{i + 1} score {item.get('score')}: {item.get('summary')}"
                for i, item in enumerate(state["evaluations"])
            ]
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", FINAL_SYSTEM),
                ("human", FINAL_HUMAN),
            ]
        )
        messages = prompt.format_messages(
            language_label=language_label(state["language"]),
            candidate_name=state["candidate_name"],
            role=state["role"],
            department=state["department"],
            seniority=state["seniority"],
            overall_score=overall_score,
            evaluations=evaluations_text or "None",
        )
        narrative = narrator.invoke(messages)
        report = {
            "overall_score": overall_score,
            **narrative.model_dump(),
        }
    else:
        report = {
            "overall_score": overall_score,
            "recommendation": "consider" if overall_score >= 6 else "needs_review",
            "strengths": (
                ["Shows potential in the role context."]
                if state["language"] == "en"
                else ["Muestra potencial en el contexto del rol."]
            ),
            "gaps": (
                ["Needs deeper and more concrete examples in some answers."]
                if state["language"] == "en"
                else ["Necesita ejemplos mas profundos y concretos en algunas respuestas."]
            ),
            "summary": (
                "Fallback summary generated because Anthropic is not configured."
                if state["language"] == "en"
                else "Resumen alternativo generado porque Anthropic no esta configurado."
            ),
        }

    return {
        "final_report": report,
        "is_finished": True,
    }


def _start_router(state: InterviewState) -> str:
    if state.get("last_answer"):
        return "evaluate_answer"
    return "generate_question"


def _next_router(state: InterviewState) -> str:
    if state["question_index"] >= state["num_questions"]:
        return "finalize"
    return "generate_question"


def build_graph():
    builder = StateGraph(InterviewState)
    builder.add_node("generate_question", generate_question)
    builder.add_node("evaluate_answer", evaluate_answer)
    builder.add_node("finalize", finalize)

    builder.add_conditional_edges(
        START,
        _start_router,
        {
            "evaluate_answer": "evaluate_answer",
            "generate_question": "generate_question",
        },
    )
    builder.add_conditional_edges(
        "evaluate_answer",
        _next_router,
        {
            "finalize": "finalize",
            "generate_question": "generate_question",
        },
    )
    builder.add_edge("generate_question", END)
    builder.add_edge("finalize", END)
    return builder.compile()
