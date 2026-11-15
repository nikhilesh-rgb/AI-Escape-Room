"""Version 1: the LLM is the whole game.

Everything the game knows (room, clues, solutions, rules) lives inside one
system prompt, and the only memory is the chat history. This is simple and
fun, but nothing outside the LLM enforces the rules. Version 2 fixes that.
"""
from __future__ import annotations

ESCAPE_TOKEN = "[ESCAPED]"

INTRO = (
    "You wake up on the cold floor of a locked library. Dust hangs in the lamplight. "
    "You can see a desk, a bookshelf, a painting and a heavy door with a four-digit keypad. "
    "Type what you want to do, for example: *examine the bookshelf*."
)

SYSTEM_PROMPT = f"""You are the Game Master of a text escape room. The player is locked in an old library.
Stay in character, write in second person, present tense, 2 to 4 sentences per reply.

THE ROOM (secret, only reveal through play):
- Desk: examining it shows a drawer with a four-digit combination lock.
- Bookshelf: four red-spined books are shelved upside down. Inside their covers are handwritten
  numbers 2, 7, 1, 8 (in shelf order). The drawer code is therefore 2718.
- Drawer (locked until the player enters 2718): contains a brass key and a folded letter.
  The letter says: "The last two digits of the way out are 96."
- Painting: a stormy seascape hanging crooked. If the player moves it, a small steel safe is revealed.
- Safe: opens only with the brass key. Inside is a card: "The first two digits of the way out are 40."
- Door: four-digit keypad. The correct code is 4096 (card digits 40 + letter digits 96).

RULES:
1. Never reveal a clue, number or solution before the player has discovered it by playing.
2. Remember what the player has already done, found and collected during this conversation.
3. The player can only use items they have collected.
4. If the player enters 4096 on the door, they escape. Describe the escape and end your message
   with the exact token {ESCAPE_TOKEN}. Never output that token at any other time.
5. Do not invent new objects, clues or puzzles.
"""


def play_turn(llm, history: list[dict], player_text: str) -> tuple[str, bool]:
    """Send one player message and return (game_master_reply, escaped)."""
    history.append({"role": "user", "content": player_text})
    reply = llm.generate(SYSTEM_PROMPT, history, temperature=0.8)
    escaped = ESCAPE_TOKEN in reply
    clean = reply.replace(ESCAPE_TOKEN, "").strip()
    history.append({"role": "assistant", "content": clean})
    return clean, escaped
