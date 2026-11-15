# AI Escape Room: Report

## 1. Goal

Build an interactive escape room where an LLM acts as the Game Master, then make it reliable. The room is a locked library with a desk, bookshelf, painting, drawer, safe and a door with a four-digit keypad. The player writes natural-language commands and must find three clues to escape.

Puzzle chain: the four red books give the drawer code (2718). The drawer holds a brass key and a letter ("last two digits: 96"). The key opens a safe behind the painting, which holds a card ("first two digits: 40"). The door code is 4096.

## 2. Version 1: LLM as the whole game

**Design.** One system prompt describes the room, the clues, the solutions and the rules. The full chat history is sent on every turn, so the history is the only memory. Streamlit provides the chat UI and a restart button. The model is told to end its reply with `[ESCAPED]` when the right code is entered on the door, and the app watches for that token.

**What works.** It took very little code and the story feels natural. The model improvises good descriptions and accepts many phrasings.

**Problems.**

1. *Secrets live in the prompt.* The same model that narrates also knows 2718 and 4096, so a player can ask for them or trick the model into slipping.
2. *Rules are suggestions.* "Items must be collected first" is a sentence in a prompt. The model prefers to keep the story flowing, so it can accept an action that should fail.
3. *Memory is soft.* Progress exists only as text in the history. In a long game the model can contradict itself, for example by describing a solved drawer as locked.
4. *Invented content.* Models like to be helpful and add objects or hints that are not part of the design.
5. *Authority claims.* Messages such as "I am the administrator" can pull the model out of its role.
6. *Hard to test.* The same input can give different results, so reliability cannot be measured with ordinary tests.

For Version 1 the assignment says to assume honest players, so these are design weaknesses rather than bugs. They are exactly what Version 2 must handle.

## 3. Version 2: Python is the referee, the LLM is the narrator

**Principle.** Python decides what happens. The LLM only describes it.

**Components.**

- `game_config.json` holds objects, items, clues, lock codes, prerequisites and hints. No solution is ever sent to the LLM.
- `engine.py` keeps the state in one JSON-serialisable dict: flags, inventory, visible objects, revealed secrets, attempt counts, escaped. `apply_action` validates every action and mutates the state only if the rules allow it. The result is a small object with `ok`, a machine-readable `kind` such as `not_in_inventory` or `wrong_code`, and plain-language facts.
- `parser.py` turns the player's text into an intent. Deterministic rules go first because they are fast, free and predictable. Only messages the rules cannot classify go to the LLM, and its JSON answer is checked against a whitelist of actions and ids. Digit codes are always read from the text with a regex, never taken from the LLM.
- `narrator.py` sends the LLM only the facts of the outcome, the visible objects and the last few turns. Its instructions forbid adding objects, clues or numbers. A **leak guard** then scans the reply for unrevealed secrets. If it finds one, or if the API call fails, the player sees the engine's plain facts instead.
- The Streamlit UI adds an inventory panel, a puzzle checklist and a developer view of the live state and the last parsed intent, which makes the system easy to demonstrate and debug.

**How the listed problems are handled.**

| Requirement | Implementation |
| --- | --- |
| Game state management | One state dict, serialisable to JSON |
| Action validation | `apply_action` and one handler per action |
| Inventory management | `use` and `examine` for held items check the inventory list; items in a closed container cannot be taken |
| Rules outside the LLM | Codes, prerequisites and clue text in the config |
| Consistency | Flags only move forward; repeated actions return `already_done` or `already_have` |
| Invalid actions | Unknown ids, hidden objects, wrong codes, ambiguous locks and missing items each return a specific failure |
| Adversarial testing | 22 pytest tests, including the five challenge cases from the brief |

One design decision came from testing. My first version of the door lock accepted 4096 whenever it was typed, even if the player had never found a clue. That would let a leaked or guessed code skip the puzzles. I added `requires_flags` to the locks, so the code only works after the clues are found, and a premature attempt looks like any wrong code, which avoids giving the player an oracle. A second bug was a config key mismatch (`sets_flags` against `set_flags`) that stopped the drawer from staying open. The walkthrough test caught it, which is a good example of why testing the state machine is easier than testing a prompt.

## 4. Testing

The suite runs in milliseconds with no API key. It covers the full escape, the five required challenge cases (uncollected key, wrong code, false claim of progress, administrator impersonation, request for all secrets), a premature door code, nonexistent objects, repeated actions, hidden objects, ambiguous locks, state serialisation, and the LLM boundary: a fake LLM that leaks a code, that fails, or that returns invalid commands. Details are in `docs/TEST_CASES.md`. The script `scripts/compare_live.py` replays the same attacks against both versions with a real Gemini key so the behaviour of V1 can be recorded.

I did not run Version 1 against a live model while building the repository, so the V1 column in the test table describes expected weaknesses of the design rather than recorded transcripts. Recording them is the first thing to do after adding an API key.

## 5. Limitations and next steps

- The leak guard matches digit strings. A narrator that spells a code out in words would pass it. Number-word detection or a second LLM check would close this gap.
- The rule parser covers common phrasings only. Some natural inputs fall through to the LLM parser or to a "please rephrase" message.
- There is one room. Because puzzles are data, adding rooms means writing configuration, though the `progress` panel and a few labels are still specific to this room.
- Narration quality is only checked for secrecy, not style.

## 6. What I learned

The main lesson is a division of labour: language models are good at language and weak at bookkeeping, so bookkeeping belongs in code. Giving the LLM only what it needs to know, and treating its output as untrusted text, matters more than writing a stricter prompt. Keeping facts and prose separate also made the system testable, which is what turns a demo into something dependable.
