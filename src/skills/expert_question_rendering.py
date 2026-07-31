from __future__ import annotations

from .catalog import SkillDefinition


def expert_questions_markdown(definition: SkillDefinition) -> str:
    if not definition.expert_questions:
        return ""
    lines = ["Expert clarification questions:"]
    for question in definition.expert_questions:
        lines.extend(
            [
                f"- `{question.required_input}`",
                f"  - English: {question.en}",
                f"  - Korean: {question.ko}",
            ]
        )
    return "\n".join(lines)


def expert_question_reference_lines(definition: SkillDefinition) -> list[str]:
    if not definition.expert_questions:
        return []
    return [
        "- Expert clarification questions:",
        *[
            line
            for question in definition.expert_questions
            for line in (
                f"  - `{question.required_input}`",
                f"    - English: {question.en}",
                f"    - Korean: {question.ko}",
            )
        ],
    ]


def expert_question_payloads(definition: SkillDefinition) -> list[dict[str, object]]:
    return [
        {
            "required_input": question.required_input,
            "questions": {"en": question.en, "ko": question.ko},
        }
        for question in definition.expert_questions
    ]


def copy_expert_question_payloads(payloads: object) -> list[dict[str, object]]:
    return [
        {"required_input": item["required_input"], "questions": dict(item["questions"])}
        for item in payloads
    ]


def domain_expert_question_body(context: dict[str, object] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    workflow = context.get("workflow_hint")
    required_input = context.get("required_input")
    question = context.get("question")
    if not isinstance(workflow, str) or not workflow:
        return None
    if not isinstance(required_input, str) or not required_input:
        return None
    if not isinstance(question, dict):
        return None
    text = question.get("text")
    if not isinstance(text, str) or not text:
        return None
    return f"Target workflow: {workflow}\nRequired input: {required_input}\n\n{text}"
