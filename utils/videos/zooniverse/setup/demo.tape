# ─────────────────────────────────────────────────────────────────────────────
# VHS tape — wildintel-tools Zooniverse demo: Step 0
# Usage:  vhs utils/videos/zooniverse/setup/demo.tape
# Output: docs/videos/zooniverse/setup.gif
#
# Requirements:
#   brew install vhs          (macOS)
#   sudo apt install vhs      (Linux / snap)
#   https://github.com/charmbracelet/vhs
# ─────────────────────────────────────────────────────────────────────────────

Output docs/videos/zooniverse/setup.gif

# ── Terminal appearance ───────────────────────────────────────────────────────
Set Theme          "Catppuccin Mocha"
Set FontSize       13
Set FontFamily     "Source Code Pro"
Set Width          1100
Set Height         650
Set WindowBar      Colorful
Set WindowBarSize  36
Set Padding        16
Set CursorBlink    false
Set TypingSpeed    40ms
Set Framerate      20

# ── Recording ────────────────────────────────────────────────────────────────

Hide
  Type "clear"
  Enter
  Sleep 300ms
Show

Type "bash utils/videos/zooniverse/setup/demo.sh"
Enter

# Wait for the script to finish (~30s measured + 3s margin).
Sleep 33s
