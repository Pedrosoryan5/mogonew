LDPlayer Priority Auto Clicker v5 - v9.3 AVOID

BASE:
- Original uploaded v5.

ONLY CHANGE:
- AVOID logic was replaced with the slot-aware behavior modeled after v9.3.

UNCHANGED:
- v5 target detection
- v5 highest multiplier behavior
- v5 templates
- v5 timing
- v5 UI
- v5 x1/x5/x10 system
- all other v5 logic

NEW AVOID BEHAVIOR:
- Checked Avoid targets are mapped to the closest configured roll slot.
- That roll slot is blocked.
- The bot chooses a different configured fallback.
- If every configured fallback is blocked, it waits instead of intentionally
  clicking a blocked slot.

Example:
RR appears closest to x1.
CHANCE appears closest to x5.
Both are checked under Avoid.

Blocked:
x1, x5

Available:
x10

=> bot chooses x10.

Run:
py auto_clicker_v5_v93_avoid.py
