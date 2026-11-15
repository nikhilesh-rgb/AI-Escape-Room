"""Version 1 Streamlit UI.  Run with:  streamlit run v1/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from common.llm import GeminiClient, LLMError
from v1.game_master import INTRO, play_turn

st.set_page_config(page_title="AI Escape Room v1", page_icon="🔐")
st.title("🔐 AI Escape Room (Version 1)")


def reset():
    st.session_state.history = []
    st.session_state.display = [("assistant", INTRO)]
    st.session_state.escaped = False


if "history" not in st.session_state:
    reset()

try:
    if "llm" not in st.session_state:
        st.session_state.llm = GeminiClient()
except LLMError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.header("How to play")
    st.write(
        "You are locked in a library. Explore, collect items, solve the puzzles and "
        "enter the code on the door. Write what you do in plain English."
    )
    st.caption("Try: examine the desk, take the key, use the key on the safe, enter 1234 on the door.")
    if st.button("Restart game"):
        reset()
        st.rerun()

for role, text in st.session_state.display:
    with st.chat_message(role):
        st.markdown(text)

if st.session_state.escaped:
    st.success("You escaped! Press 'Restart game' to play again.")
elif prompt := st.chat_input("What do you do?"):
    st.session_state.display.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            reply, escaped = play_turn(st.session_state.llm, st.session_state.history, prompt)
        except LLMError as exc:
            reply, escaped = f"(The Game Master is unavailable: {exc})", False
            st.session_state.history.pop()  # drop the unanswered user turn
        st.markdown(reply)
    st.session_state.display.append(("assistant", reply))
    if escaped:
        st.session_state.escaped = True
        st.balloons()
        st.rerun()
