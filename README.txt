LDPlayer Priority Auto Clicker v5

NEW:
- Multiple disabled targets now remain disabled together.
- Highest visible multiplier logic applies to every priority target, not just RR/CC.
- Added x1, x5 and x10 fallback points.
- Normal fallback can be x1/x5/x10.
- If any disabled target such as RR or CHANCE is visible, the bot can use a different roll multiplier such as x10.

IMPORTANT:
For highest-multiplier target selection, add digit templates:
DIGIT_0.png through DIGIT_9.png

Example:
Priority RR
Visible RR 200x and RR 1000x
=> selects RR 1000x if digits are recognized.

Example avoid setup:
Disable RR + CHANCE
Normal fallback = x1
If avoided target is visible = x10
=> RR and CHANCE are not intentionally clicked; the fallback uses x10 while either avoided template is visible.

Set x1/x5/x10 using Pick x1, Pick x5 and Pick x10 from screenshot.

Install:
py -m pip install -r requirements.txt

Run:
py auto_clicker_v5.py
