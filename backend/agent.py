"""
Bounded Q&A agent. Deliberately NOT a graph/orchestration framework --
this is a single tool-calling loop because the only job here is to
answer questions about already-computed results using a small, fixed,
read-only toolset. Code has already made every money decision before
this module is ever called.

MOCK MODE: if no LLM_API_KEY is set, falls back to simple keyword
routing over the same tool registry, so "Ask ReconPilot" still works
without any API key configured.

PROVIDER SUPPORT: Supports both Groq (default) and Anthropic.
Set LLM_PROVIDER=groq or LLM_PROVIDER=anthropic in .env.
Groq uses the OpenAI-compatible SDK; Anthropic uses its own SDK.
"""
import json
import re

from .agent_tools import (
    TOOL_REGISTRY,
    explain_matching_rule,
    get_batch_summary,
    get_cash_forecast,
    get_unresolved_value,
    list_exceptions,
)
from .config import settings

AGENT_POLICY = (
    "You can only report evidence already computed by deterministic code. "
    "You cannot approve, refund, settle, or alter any record. "
    "If evidence is unavailable, say the available data is insufficient. "
    "Never speculate about fraud or intent."
)

_RECORD_ID_RE = re.compile(r"\bORDER-\d{4}\b")

# Shared tool schemas (OpenAI-compatible format used by Groq)
_TOOLS_OPENAI = [
    {"type": "function", "function": {
        "name": "get_batch_summary",
        "description": "Get summary counts for a batch.",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string"}}, "required": ["batch_id"]}}},
    {"type": "function", "function": {
        "name": "get_record_details",
        "description": "Get full details for one record.",
        "parameters": {"type": "object", "properties": {
            "record_id": {"type": "string"}, "batch_id": {"type": "string"}},
            "required": ["record_id", "batch_id"]}}},
    {"type": "function", "function": {
        "name": "list_exceptions",
        "description": "List exception records, optionally filtered by type.",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string"}, "exception_type": {"type": "string"}},
            "required": ["batch_id"]}}},
    {"type": "function", "function": {
        "name": "get_unresolved_value",
        "description": "Get total unresolved value for a batch.",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string"}}, "required": ["batch_id"]}}},
    {"type": "function", "function": {
        "name": "explain_matching_rule",
        "description": "Explain why a record got its decision.",
        "parameters": {"type": "object", "properties": {
            "record_id": {"type": "string"}, "batch_id": {"type": "string"}},
            "required": ["record_id", "batch_id"]}}},
    {"type": "function", "function": {
        "name": "get_cash_forecast",
        "description": "Project forward cash position from batch results.",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string"}, "horizon_days": {"type": "integer"}},
            "required": ["batch_id"]}}},
]


def _mock_answer(question: str, batch_id: str, output_dir: str) -> dict:
    """Rule-based fallback used when no LLM API key is configured."""
    q = question.lower()
    match = _RECORD_ID_RE.search(question.upper())

    if match:
        record_id = match.group(0)
        result = explain_matching_rule(record_id, batch_id, output_dir)
        if "decision" not in result:
            return {"answer": result["explanation"], "tool_calls": ["explain_matching_rule"]}
        answer = (
            f"Record {record_id}: decision={result['decision']}, "
            f"rule applied={result['rule_applied']}, "
            f"review required={result['review_required']}. "
            f"Evidence: {result['evidence']}. Action executed: None."
        )
        return {"answer": answer, "tool_calls": ["explain_matching_rule"]}

    if "unresolved" in q or "value" in q:
        result = get_unresolved_value(batch_id, output_dir)
        answer = (
            f"{result['unresolved_records']} records are unresolved, "
            f"totalling {result['unresolved_value_paise']} paise "
            f"(₹{result['unresolved_value_paise']/100:,.2f}) in unresolved value."
        )
        return {"answer": answer, "tool_calls": ["get_unresolved_value"]}

    if any(kw in q for kw in ("forecast", "cash", "projection", "inflow", "position")):
        result = get_cash_forecast(batch_id, output_dir=output_dir)
        answer = (
            f"Cash forecast for batch {batch_id} (next {result['forecast_horizon_days']} days): "
            f"Settled: {result['settled_inr']}, "
            f"Expected inflow: ₹{result['expected_inflow_paise']/100:,.2f}, "
            f"At-risk: ₹{result['at_risk_paise']/100:,.2f}, "
            f"Projected total: {result['projected_total_inr']}. "
            f"{result['excluded_records']} records excluded from forecast."
        )
        return {"answer": answer, "tool_calls": ["get_cash_forecast"]}

    if "exception" in q:
        result = list_exceptions(batch_id, output_dir=output_dir)
        if not result:
            return {"answer": "No exceptions found for this batch.", "tool_calls": ["list_exceptions"]}
        by_type = {}
        for r in result:
            by_type[r["exception_code"]] = by_type.get(r["exception_code"], 0) + 1
        breakdown = ", ".join(f"{k}: {v}" for k, v in by_type.items())
        return {"answer": f"{len(result)} exceptions found. Breakdown -> {breakdown}.",
                "tool_calls": ["list_exceptions"]}

    # default: batch summary
    result = get_batch_summary(batch_id, output_dir)
    answer = (
        f"Batch {result['batch_id']}: {result['total_records']} records, "
        f"{result['exact_matches']} exact matches, {result['probable_matches']} probable matches, "
        f"{result['exceptions']} exceptions. Ask about a specific record (e.g. 'why is ORDER-0042 an exception?'), "
        f"'unresolved value', 'cash forecast', or 'list exceptions' for more detail."
    )
    return {"answer": answer, "tool_calls": ["get_batch_summary"]}


def _run_tool(name: str, args: dict, output_dir: str) -> str:
    """Execute a tool from the registry and return its result as a string."""
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        result = fn(**{**args, "output_dir": output_dir})
        return json.dumps(result, default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def _ask_groq(question: str, batch_id: str, output_dir: str) -> dict:
    """Tool-calling loop using Groq's OpenAI-compatible API."""
    try:
        from groq import Groq
    except ImportError:
        result = _mock_answer(question, batch_id, output_dir)
        result["mode"] = "MOCK (groq package not installed — run: pip install groq)"
        return result

    client = Groq(api_key=settings.llm_api_key)
    messages = [
        {"role": "system", "content": AGENT_POLICY},
        {"role": "user", "content": f"{question}\n\n(batch_id={batch_id})"},
    ]
    tool_calls_made = []

    for _ in range(5):  # bounded loop
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=_TOOLS_OPENAI,
            tool_choice="auto",
            max_tokens=800,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return {"answer": msg.content or "", "tool_calls": tool_calls_made, "mode": "LIVE_LLM (Groq)"}

        # Append assistant message with tool calls
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

        # Execute each tool call and append results
        for tc in msg.tool_calls:
            tool_calls_made.append(tc.function.name)
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            result_str = _run_tool(tc.function.name, args, output_dir)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

    return {"answer": "Reached tool-call limit without a final answer.", "tool_calls": tool_calls_made, "mode": "LIVE_LLM (Groq)"}


def _ask_anthropic(question: str, batch_id: str, output_dir: str) -> dict:
    """Tool-calling loop using Anthropic's Claude API."""
    try:
        import anthropic
    except ImportError:
        result = _mock_answer(question, batch_id, output_dir)
        result["mode"] = "MOCK (anthropic package not installed)"
        return result

    # Convert OpenAI tool schema to Anthropic format
    tools_schema = [
        {"name": t["function"]["name"],
         "description": t["function"]["description"],
         "input_schema": t["function"]["parameters"]}
        for t in _TOOLS_OPENAI
    ]

    client = anthropic.Anthropic(api_key=settings.llm_api_key)
    messages = [{"role": "user", "content": f"{question}\n\n(batch_id={batch_id})"}]
    tool_calls_made = []

    for _ in range(4):
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=600,
            system=AGENT_POLICY,
            tools=tools_schema,
            messages=messages,
        )
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return {"answer": text, "tool_calls": tool_calls_made, "mode": "LIVE_LLM (Anthropic)"}

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            tool_calls_made.append(tu.name)
            result_str = _run_tool(tu.name, tu.input, output_dir)
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result_str})
        messages.append({"role": "user", "content": tool_results})

    return {"answer": "Reached tool-call limit without a final answer.", "tool_calls": tool_calls_made, "mode": "LIVE_LLM (Anthropic)"}


def ask(question: str, batch_id: str, output_dir: str = "data/output") -> dict:
    """Public entry point used by the API/UI.

    Routes to:
    - Mock router       if no LLM_API_KEY is set
    - Groq API          if LLM_PROVIDER=groq  (default)
    - Anthropic API     if LLM_PROVIDER=anthropic
    """
    if settings.llm_mock_mode:
        result = _mock_answer(question, batch_id, output_dir)
        result["mode"] = "MOCK"
        return result

    if settings.llm_provider == "anthropic":
        return _ask_anthropic(question, batch_id, output_dir)

    return _ask_groq(question, batch_id, output_dir)
