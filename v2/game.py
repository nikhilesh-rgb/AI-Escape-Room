"""One turn of Version 2: parse, validate, narrate."""
from __future__ import annotations

from v2.engine import apply_action
from v2.narrator import narrate
from v2.parser import parse_intent


def play_turn(text: str, state: dict, cfg: dict, llm=None, history: list | None = None) -> dict:
    intent = parse_intent(text, state, cfg, llm)
    result = apply_action(state, intent, cfg)
    reply = narrate(text, result, state, cfg, llm, history)
    if history is not None:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
    return {"reply": reply, "intent": intent, "result": result}
