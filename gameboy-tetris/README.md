# Tetris Boy

A Game Boy (DMG) styled Tetris game built for mobile browsers, with a monochrome
green dot-matrix screen, on-screen D-pad / A / B controls, chiptune sound
effects, and haptic feedback.

## Play it

Just open `index.html` in a browser, or serve the folder:

```sh
cd gameboy-tetris
python3 -m http.server 8000
```

Then visit `http://localhost:8000` on your phone (or use your computer's
local network IP to load it on a phone).

## Controls

- **D-pad**: left / right move, down = soft drop, up = hard drop
- **A**: rotate clockwise
- **B**: rotate counter-clockwise
- **START**: begin / pause / resume
- **SELECT**: restart
- 🔊 button: mute/unmute sound

Keyboard also works for testing on desktop: arrow keys to move, `X`/`Up` to
rotate CW, `Z` to rotate CCW, `Space` for hard drop, `Enter`/`P` to start or
pause, `R`/`Shift` to restart.

## Features

- Standard 10x20 board, 7-bag randomizer, wall-kick rotation, ghost piece,
  level-based speed-up, and classic scoring (single/double/triple/tetris).
- High score persisted in `localStorage`.
- Fully self-contained (no build step, no dependencies).
