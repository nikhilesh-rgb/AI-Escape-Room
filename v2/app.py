"""Version 2 Streamlit UI.  Run with:  streamlit run v2/app.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from common.llm import get_client_or_none
from v2.engine import load_config, new_state, progress
from v2.game import play_turn

st.set_page_config(page_title="AI Escape Room v2", page_icon="🔐")
st.title("🔐 AI Escape Room (Version 2)")

cfg = load_config()


def reset():
    st.session_state.state = new_state(cfg)
    st.session_state.history = []
    st.session_state.display = [("assistant", cfg["intro"])]
    st.session_state.last = None


if "state" not in st.session_state:
    reset()
if "llm" not in st.session_state:
    st.session_state.llm = get_client_or_none()
llm = st.session_state.llm
state = st.session_state.state

with st.sidebar:
    st.header("How to play")
    st.write(
        "You are locked in a library. Explore, collect items, solve the puzzles and "
        "enter the four-digit code on the door. Write what you do in plain English."
    )
    st.caption("Try: look around, examine the desk, take the key, use the key on the safe, enter 1234 on the door. Ask for a hint if you get stuck.")
    if st.button("Restart game"):
        reset()
        st.rerun()
    st.subheader("Inventory")
    st.write(", ".join(cfg["items"][i]["name"] for i in state["inventory"]) or "empty")
    st.subheader("Progress")
    for label, done in progress(state).items():
        st.write(("✅ " if done else "⬜ ") + label)
    if llm is None:
        st.info("Offline mode: no Gemini key found, so replies use plain templates. Add GEMINI_API_KEY to .env for the AI Game Master.")
    with st.expander("Developer view (game state)"):
        if st.session_state.last:
            st.caption("Last intent")
            st.json(st.session_state.last["intent"])
            st.caption(f"Engine result: {st.session_state.last['result'].kind}")
        st.caption("State (the single source of truth)")
        st.code(json.dumps(state, indent=2), language="json")

for role, text in st.session_state.display:
    with st.chat_message(role):
        st.markdown(text)

if state["escaped"]:
    st.success("You escaped! Press 'Restart game' to play again.")
elif prompt := st.chat_input("What do you do?"):
    out = play_turn(prompt, state, cfg, llm, st.session_state.history)
    st.session_state.last = out
    st.session_state.display += [("user", prompt), ("assistant", out["reply"])]
    if state["escaped"]:
        st.balloons()
    st.rerun()
