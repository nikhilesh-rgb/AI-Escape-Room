"""Version 2 game engine: structured state, rules and action validation.

Python decides whether an action succeeds. The LLM never changes state, it only
describes the outcome (see narrator.py). All puzzle solutions live in
game_config.json and are never sent to the LLM.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("game_config.json")

ACTIONS = {
    "look", "examine", "take", "use", "open", "move", "enter_code",
    "inventory", "hint", "help", "cheat_attempt", "unknown",
}


@dataclass
class Result:
    ok: bool
    kind: str  # machine-readable reason, e.g. "success", "locked", "not_in_inventory"
    facts: list[str] = field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def new_state(cfg: dict) -> dict:
    """The whole game state is one JSON-serialisable dict."""
    return {
        "flags": [],
        "inventory": [],
        "visible": [oid for oid, o in cfg["objects"].items() if o.get("visible_at_start")],
        "revealed_secrets": [],
        "attempts": {},
        "turns": 0,
        "escaped": False,
    }


# ----------------------------------------------------------------- helpers

def _name(cfg: dict, ident: str) -> str:
    return (cfg["objects"].get(ident) or cfg["items"].get(ident))["name"]


def _matches(rule: dict, flags: list[str]) -> bool:
    return all(f in flags for f in rule.get("if_flags", [])) and not any(
        f in flags for f in rule.get("not_flags", [])
    )


def _first_rule(rules: list[dict], state: dict) -> dict | None:
    return next((r for r in rules if _matches(r, state["flags"])), None)


def _apply_effects(rule: dict, state: dict) -> None:
    for flag in rule.get("set_flags", []):
        if flag not in state["flags"]:
            state["flags"].append(flag)
    for oid in rule.get("reveals", []):
        if oid not in state["visible"]:
            state["visible"].append(oid)
    for secret in rule.get("reveals_secrets", []):
        if secret not in state["revealed_secrets"]:
            state["revealed_secrets"].append(secret)


def item_accessible(state: dict, cfg: dict, item_id: str) -> bool:
    """An item can be examined or taken when held, or when its container is open."""
    if item_id in state["inventory"]:
        return True
    return cfg["items"][item_id]["available_when"] in state["flags"]


def resolve_ids(text: str, cfg: dict) -> list[str]:
    """Find object and item ids mentioned in free text, in order of appearance."""
    lowered = text.lower()
    spans: list[tuple[int, int, str]] = []
    pairs = [(a, i) for group in (cfg["objects"], cfg["items"]) for i, o in group.items() for a in o["aliases"]]
    for alias, ident in sorted(pairs, key=lambda p: -len(p[0])):
        for m in re.finditer(rf"\b{re.escape(alias)}\b", lowered):
            if not any(s < m.end() and m.start() < e for s, e, _ in spans):
                spans.append((m.start(), m.end(), ident))
    return [ident for _, _, ident in sorted(spans)]


def find_leaks(text: str, state: dict, cfg: dict) -> list[str]:
    """Return secret strings that appear in `text` although the player has not earned them."""
    leaks = []
    candidates = cfg["secrets"]["always_hidden"] + [
        s for s in cfg["secrets"]["hidden_until_revealed"] if s not in state["revealed_secrets"]
    ]
    for secret in candidates:
        if re.search(rf"(?<!\d){re.escape(secret)}(?!\d)", text):
            leaks.append(secret)
    return leaks


# ---------------------------------------------------------------- handlers

def _look(state, intent, cfg):
    seen = [cfg["objects"][o]["name"] for o in state["visible"]]
    facts = ["You see: " + ", ".join(seen) + "."]
    if state["inventory"]:
        facts.append("You are carrying: " + ", ".join(_name(cfg, i) for i in state["inventory"]) + ".")
    return Result(True, "look", facts)


def _inventory(state, intent, cfg):
    if not state["inventory"]:
        return Result(True, "inventory", ["Your pockets are empty."])
    return Result(True, "inventory", ["You are carrying: " + ", ".join(_name(cfg, i) for i in state["inventory"]) + "."])


def _examine(state, intent, cfg):
    target = intent.get("target") or intent.get("item")
    if not target:
        return Result(False, "no_target", ["It is unclear what the player wants to examine."])
    if target in cfg["items"]:
        if not item_accessible(state, cfg, target):
            return Result(False, "not_here", [f"There is no {_name(cfg, target)} within reach."])
        entry = cfg["items"][target]
    elif target in cfg["objects"]:
        if target not in state["visible"]:
            return Result(False, "not_here", [f"There is no {_name(cfg, target)} to be seen here."])
        entry = cfg["objects"][target]
    else:
        return Result(False, "unknown_object", ["There is nothing like that in this room."])
    rule = _first_rule(entry["examine"], state)
    _apply_effects(rule, state)
    return Result(True, "success", [rule["text"]])


def _take(state, intent, cfg):
    target = intent.get("item") or intent.get("target")
    if not target:
        return Result(False, "no_target", ["It is unclear what the player wants to take."])
    if target in cfg["objects"]:
        return Result(False, "cannot_take", [f"The {_name(cfg, target)} cannot be carried away."])
    if target not in cfg["items"]:
        return Result(False, "unknown_object", ["There is nothing like that in this room."])
    if target in state["inventory"]:
        return Result(False, "already_have", [f"The player already has the {_name(cfg, target)}."])
    if not item_accessible(state, cfg, target):
        return Result(False, "not_here", [f"There is no {_name(cfg, target)} within reach."])
    state["inventory"].append(target)
    return Result(True, "success", [cfg["items"][target]["take_text"]])


def _use(state, intent, cfg):
    item, target = intent.get("item"), intent.get("target")
    if not item or item not in cfg["items"]:
        return Result(False, "no_item", ["It is unclear which item the player wants to use."])
    if item not in state["inventory"]:
        return Result(False, "not_in_inventory", [f"The player does not have the {_name(cfg, item)}."])
    if not target or target not in cfg["objects"] or target not in state["visible"]:
        return Result(False, "not_here", ["There is nothing here to use that on."])
    for rule in cfg["use_rules"]:
        if rule["item"] == item and rule["target"] == target:
            if rule["done_flag"] in state["flags"]:
                return Result(False, "already_done", [rule["done_text"]])
            _apply_effects(rule, state)
            return Result(True, "success", [rule["text"]])
    return Result(False, "no_effect", [f"Using the {_name(cfg, item)} on the {_name(cfg, target)} does nothing."])


def _open(state, intent, cfg):
    target = intent.get("target") or intent.get("item")
    if not target or target not in cfg["objects"]:
        return Result(False, "no_target", ["It is unclear what the player wants to open."])
    if target not in state["visible"]:
        return Result(False, "not_here", [f"There is no {_name(cfg, target)} to be seen here."])
    obj = cfg["objects"][target]
    rule = _first_rule(obj.get("open", []), state)
    if rule:
        _apply_effects(rule, state)
        return Result(False, "already_done", [rule["text"]])
    if "open_fail" in obj:
        return Result(False, "locked", [obj["open_fail"]])
    return Result(False, "cannot_open", [f"The {obj['name']} cannot be opened."])


def _move(state, intent, cfg):
    target = intent.get("target") or intent.get("item")
    if not target or target not in cfg["objects"]:
        return Result(False, "no_target", ["It is unclear what the player wants to move."])
    if target not in state["visible"]:
        return Result(False, "not_here", [f"There is no {_name(cfg, target)} to be seen here."])
    obj = cfg["objects"][target]
    rule = _first_rule(obj.get("move", []), state)
    if not rule:
        return Result(False, "no_effect", [f"Moving the {obj['name']} achieves nothing."])
    already = "painting_moved" in state["flags"]
    _apply_effects(rule, state)
    return Result(not already, "already_done" if already else "success", [rule["text"]])


def _enter_code(state, intent, cfg):
    code = re.sub(r"\D", "", intent.get("code") or "")
    if not code:
        return Result(False, "no_code", ["The player did not say which digits to enter."])
    target = intent.get("target")
    if target is None:
        open_locks = [
            o for o in state["visible"]
            if "lock" in cfg["objects"][o] and cfg["objects"][o]["lock"]["done_flag"] not in state["flags"]
        ]
        if len(open_locks) != 1:
            return Result(False, "ambiguous_target", ["It is unclear which lock the player is trying. There is more than one."])
        target = open_locks[0]
    if target not in cfg["objects"] or target not in state["visible"]:
        return Result(False, "not_here", ["There is no such lock to be seen here."])
    lock = cfg["objects"][target].get("lock")
    if not lock:
        return Result(False, "no_lock", [f"The {_name(cfg, target)} has no lock that takes a code."])
    if lock["done_flag"] in state["flags"]:
        return Result(False, "already_done", [f"The {_name(cfg, target)} is already unlocked."])
    # The code only works once the player has earned it by finding the clues.
    earned = all(f in state["flags"] for f in lock.get("requires_flags", []))
    if code != lock["code"] or not earned:
        state["attempts"][target] = state["attempts"].get(target, 0) + 1
        return Result(False, "wrong_code", [lock["fail"]])
    _apply_effects(lock, state)
    if lock.get("ends_game"):
        state["escaped"] = True
    return Result(True, "success", [lock["success"]])


def _hint(state, intent, cfg):
    rule = _first_rule(cfg["hints"], state)
    return Result(True, "hint", [rule["text"]])


def _help(state, intent, cfg):
    return Result(True, "help", [
        "You can examine objects, take items, use an item on an object, open or move things, "
        "enter a four-digit code on a lock, check your inventory, look around or ask for a hint."
    ])


def _cheat(state, intent, cfg):
    return Result(False, "refused", [
        "That is not something the player can do from inside the room. "
        "The game rules cannot be changed by talking, and secrets stay secret until they are found."
    ])


def _unknown(state, intent, cfg):
    return Result(False, "not_understood", [
        "It is unclear what the player wants to do. Try examining, taking, using or opening something."
    ])


HANDLERS = {
    "look": _look, "examine": _examine, "take": _take, "use": _use, "open": _open,
    "move": _move, "enter_code": _enter_code, "inventory": _inventory, "hint": _hint,
    "help": _help, "cheat_attempt": _cheat, "unknown": _unknown,
}


def apply_action(state: dict, intent: dict, cfg: dict) -> Result:
    """Validate an intent against the state and rules, mutate the state, return the outcome."""
    if state["escaped"]:
        return Result(False, "game_over", ["The player has already escaped. The game is over."])
    state["turns"] += 1
    action = intent.get("action") if intent.get("action") in ACTIONS else "unknown"
    return HANDLERS[action](state, intent, cfg)


def progress(state: dict) -> dict[str, bool]:
    """Puzzle checklist shown in the UI."""
    f = state["flags"]
    return {
        "Found the drawer code (books)": "books_examined" in f,
        "Opened the drawer": "drawer_open" in f,
        "Found the safe (painting)": "painting_moved" in f,
        "Opened the safe": "safe_open" in f,
        "Door unlocked": "door_unlocked" in f,
    }
