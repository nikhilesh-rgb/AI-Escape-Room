"""V1 has no engine to test, so these only check the plumbing around the LLM."""
from v1.game_master import ESCAPE_TOKEN, SYSTEM_PROMPT, play_turn


class Scripted:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def generate(self, system, messages, temperature=0.7, json_mode=False):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def test_history_is_sent_back_each_turn():
    llm, history = Scripted(["You see a desk.", "A drawer."]), []
    play_turn(llm, history, "look")
    play_turn(llm, history, "examine desk")
    assert len(llm.seen[1]) == 3  # user, assistant, user


def test_escape_token_is_detected_and_hidden():
    llm = Scripted([f"The door swings open. {ESCAPE_TOKEN}"])
    reply, escaped = play_turn(llm, [], "enter 4096")
    assert escaped and ESCAPE_TOKEN not in reply


def test_v1_prompt_contains_solutions_which_is_its_weakness():
    # Documented limitation: in V1 the secrets live inside the prompt itself.
    assert "4096" in SYSTEM_PROMPT and "2718" in SYSTEM_PROMPT
