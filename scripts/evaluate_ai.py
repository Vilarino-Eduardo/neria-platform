"""Executa uma homologação curta e reproduzível do provedor real de IA."""

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from openai import APIConnectionError, AuthenticationError, RateLimitError

from app.core.settings import get_settings
from app.services.ai.contracts import AIMessage, AIRequest, RetrievedKnowledge
from app.services.ai.openai_provider import OpenAIResponsesProvider

SYSTEM_INSTRUCTIONS = """Você é a assistente de atendimento da Loja Piloto.
Responda apenas com informações fornecidas na base de conhecimento.
Não invente preços, prazos, políticas ou disponibilidade.
Quando não houver informação suficiente, marque transferência para atendimento humano.
Seja objetiva, cordial e responda em português do Brasil."""
MAX_OUTPUT_TOKENS_PER_SCENARIO = 300
DEFAULT_SUITE_PATH = Path(__file__).resolve().parents[1] / "evaluations" / "commercial_v1.json"


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    knowledge: str
    expected_handoff: bool
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()


def load_scenarios(path: Path = DEFAULT_SUITE_PATH) -> tuple[Scenario, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = tuple(
        Scenario(
            name=item["name"],
            question=item["question"],
            knowledge=item["knowledge"],
            expected_handoff=item["expected_handoff"],
            required_terms=tuple(item.get("required_terms", ())),
            forbidden_terms=tuple(item.get("forbidden_terms", ())),
            expected_source_ids=tuple(item.get("expected_source_ids", ())),
        )
        for item in payload["scenarios"]
    )
    names = [scenario.name for scenario in scenarios]
    if not scenarios or len(names) != len(set(names)):
        raise ValueError("A suíte deve conter cenários com nomes únicos.")
    return scenarios


SCENARIOS = load_scenarios()


def evaluate_scenario(
    scenario: Scenario,
    *,
    answer: str,
    should_handoff: bool,
    source_ids: tuple[str, ...] = (),
) -> bool:
    normalized = answer.casefold()
    required_ok = not scenario.required_terms or any(
        term.casefold() in normalized for term in scenario.required_terms
    )
    forbidden_ok = not any(
        term.casefold() in normalized for term in scenario.forbidden_terms
    )
    sources_ok = (
        not scenario.expected_source_ids
        or set(source_ids) == set(scenario.expected_source_ids)
    )
    return (
        should_handoff == scenario.expected_handoff
        and required_ok
        and forbidden_ok
        and sources_ok
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-paid-api",
        action="store_true",
        help=(
            f"Confirma conscientemente a execução de {len(SCENARIOS)} chamadas pagas à API."
        ),
    )
    parser.add_argument(
        "--scenario",
        choices=[scenario.name for scenario in SCENARIOS],
        help="Executa somente o cenário informado; por padrão executa todos.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_paid_api:
        print(
            json.dumps(
                {
                    "error": (
                        "Execução bloqueada para evitar custos. Use --confirm-paid-api "
                        "somente após autorização explícita."
                    )
                },
                ensure_ascii=False,
            )
        )
        return 2
    settings = get_settings()
    if not settings.openai_api_key:
        print(json.dumps({"error": "OPENAI_API_KEY não configurada."}, ensure_ascii=False))
        return 2

    provider = OpenAIResponsesProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        max_output_tokens=MAX_OUTPUT_TOKENS_PER_SCENARIO,
    )
    selected_scenarios = tuple(
        scenario
        for scenario in SCENARIOS
        if args.scenario is None or scenario.name == args.scenario
    )
    results = []
    for scenario in selected_scenarios:
        started_at = time.perf_counter()
        try:
            result = provider.generate(
                AIRequest(
                    system_instructions=SYSTEM_INSTRUCTIONS,
                    messages=[AIMessage(role="user", content=scenario.question)],
                    knowledge=[
                        RetrievedKnowledge(
                            chunk_id="evaluation",
                            source_title="Política da Loja Piloto",
                            content=scenario.knowledge,
                            score=1.0,
                        )
                    ],
                )
            )
        except AuthenticationError:
            print(json.dumps({"error": "OPENAI_API_KEY inválida."}, ensure_ascii=False))
            return 2
        except RateLimitError as exc:
            code = getattr(exc, "code", None)
            message = (
                "Cota da API insuficiente. Ative créditos de faturamento na OpenAI."
                if code == "insufficient_quota"
                else "Limite temporário da API atingido. Tente novamente mais tarde."
            )
            print(json.dumps({"error": message, "code": code}, ensure_ascii=False))
            return 2
        except APIConnectionError:
            print(json.dumps({"error": "Não foi possível conectar à API da OpenAI."}, ensure_ascii=False))
            return 2
        passed = evaluate_scenario(
            scenario,
            answer=result.content,
            should_handoff=result.should_handoff,
            source_ids=result.source_ids,
        )
        results.append(
            {
                "scenario": scenario.name,
                "passed": passed,
                "expected_handoff": scenario.expected_handoff,
                "answer": result.content,
                "confidence": result.confidence,
                "should_handoff": result.should_handoff,
                "source_ids": list(result.source_ids),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )

    summary = {
        "model": settings.openai_model,
        "paid_calls": len(results),
        "maximum_output_tokens_per_call": MAX_OUTPUT_TOKENS_PER_SCENARIO,
        "maximum_output_tokens_for_run": (
            len(selected_scenarios) * MAX_OUTPUT_TOKENS_PER_SCENARIO
        ),
        "passed": sum(item["passed"] for item in results),
        "total": len(selected_scenarios),
        "input_tokens": sum(item["input_tokens"] or 0 for item in results),
        "output_tokens": sum(item["output_tokens"] or 0 for item in results),
        "scenarios": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
