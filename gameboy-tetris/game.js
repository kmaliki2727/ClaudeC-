(() => {
  "use strict";

  // ---------- Constants ----------
  const COLS = 10;
  const ROWS = 20;
  const CELL = 8; // internal canvas px per board cell
  const BOARD_X = 8;
  const BOARD_Y = 8;
  const SIDE_X = 96;

  const COLORS = {
    bg: "#9bbc0f",
    boardBg: "#8bac0f",
    mid: "#306230",
    dark: "#0f380f",
  };

  const PIECES = {
    I: { cells: [[0, 1], [1, 1], [2, 1], [3, 1]] },
    O: { cells: [[1, 1], [2, 1], [1, 2], [2, 2]] },
    T: { cells: [[1, 0], [0, 1], [1, 1], [2, 1]] },
    S: { cells: [[1, 0], [2, 0], [0, 1], [1, 1]] },
    Z: { cells: [[0, 0], [1, 0], [1, 1], [2, 1]] },
    J: { cells: [[0, 0], [0, 1], [1, 1], [2, 1]] },
    L: { cells: [[2, 0], [0, 1], [1, 1], [2, 1]] },
  };
  const PIECE_TYPES = Object.keys(PIECES);

  const KICKS = [0, -1, 1, -2, 2];

  // ---------- Canvas ----------
  const canvas = document.getElementById("board");
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  // ---------- Audio ----------
  let audioCtx = null;
  let muted = localStorage.getItem("tetrisboy-muted") === "1";
  const muteBtn = document.getElementById("mute-btn");
  muteBtn.textContent = muted ? "🔇" : "🔊";

  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) audioCtx = new AC();
    }
    if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  }

  function beep(freq, dur, type = "square", vol = 0.06, delay = 0) {
    if (muted || !audioCtx) return;
    const t0 = audioCtx.currentTime + delay;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    gain.gain.setValueAtTime(vol, t0);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  const sfx = {
    move: () => beep(160, 0.03, "square", 0.03),
    rotate: () => beep(300, 0.05, "square"),
    lock: () => beep(120, 0.06, "square"),
    hardDrop: () => beep(90, 0.08, "square"),
    lineClear: (n) => {
      const base = 440;
      for (let i = 0; i < n; i++) beep(base + i * 120, 0.09, "square", 0.07, i * 0.06);
    },
    levelUp: () => {
      beep(523, 0.08, "square");
      beep(659, 0.08, "square", 0.06, 0.09);
      beep(784, 0.12, "square", 0.06, 0.18);
    },
    gameOver: () => {
      beep(300, 0.15, "square", 0.06);
      beep(220, 0.15, "square", 0.06, 0.15);
      beep(140, 0.3, "square", 0.06, 0.3);
    },
  };

  function vibrate(pattern) {
    if (navigator.vibrate) {
      try { navigator.vibrate(pattern); } catch (e) { /* ignore */ }
    }
  }

  // ---------- Game state ----------
  let grid, current, next, bag, score, level, lines, dropInterval, dropAccum,
      softDropping, gameOver, paused, started, lastTime, rafId, highScore;

  highScore = Number(localStorage.getItem("tetrisboy-highscore") || 0);

  function newBag() {
    const b = PIECE_TYPES.slice();
    for (let i = b.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [b[i], b[j]] = [b[j], b[i]];
    }
    return b;
  }

  function drawFromBag() {
    if (bag.length === 0) bag = newBag();
    return bag.pop();
  }

  function makePiece(type) {
    return {
      type,
      cells: PIECES[type].cells.map((c) => c.slice()),
      x: 3,
      y: 0,
    };
  }

  function resetGame() {
    grid = Array.from({ length: ROWS }, () => Array(COLS).fill(0));
    bag = newBag();
    current = makePiece(drawFromBag());
    next = drawFromBag();
    score = 0;
    level = 1;
    lines = 0;
    dropInterval = 800;
    dropAccum = 0;
    softDropping = false;
    gameOver = false;
    paused = false;
    started = false;
    updateOverlay();
  }

  function collides(cells, ox, oy) {
    for (const [cx, cy] of cells) {
      const bx = ox + cx;
      const by = oy + cy;
      if (bx < 0 || bx >= COLS || by >= ROWS) return true;
      if (by >= 0 && grid[by][bx]) return true;
    }
    return false;
  }

  function tryMove(dx, dy) {
    if (!collides(current.cells, current.x + dx, current.y + dy)) {
      current.x += dx;
      current.y += dy;
      return true;
    }
    return false;
  }

  function rotateCells(cells, cw) {
    return cells.map(([x, y]) => (cw ? [3 - y, x] : [y, 3 - x]));
  }

  function tryRotate(cw) {
    if (current.type === "O") return;
    const rotated = rotateCells(current.cells, cw);
    for (const k of KICKS) {
      if (!collides(rotated, current.x + k, current.y)) {
        current.cells = rotated;
        current.x += k;
        sfx.rotate();
        return true;
      }
    }
    return false;
  }

  function lockPiece() {
    for (const [cx, cy] of current.cells) {
      const bx = current.x + cx;
      const by = current.y + cy;
      if (by < 0) {
        triggerGameOver();
        return;
      }
      grid[by][bx] = 1;
    }
    sfx.lock();
    clearLines();
    spawnNext();
  }

  function clearLines() {
    let cleared = 0;
    for (let r = ROWS - 1; r >= 0; r--) {
      if (grid[r].every((c) => c)) {
        grid.splice(r, 1);
        grid.unshift(Array(COLS).fill(0));
        cleared++;
        r++;
      }
    }
    if (cleared > 0) {
      const points = [0, 40, 100, 300, 1200][cleared] * level;
      score += points;
      lines += cleared;
      const newLevel = Math.floor(lines / 10) + 1;
      if (newLevel > level) {
        level = newLevel;
        dropInterval = Math.max(100, 800 - (level - 1) * 60);
        sfx.levelUp();
      }
      sfx.lineClear(cleared);
      vibrate(cleared >= 4 ? [30, 40, 30, 40, 60] : [30]);
      if (score > highScore) {
        highScore = score;
        localStorage.setItem("tetrisboy-highscore", String(highScore));
      }
    }
  }

  function spawnNext() {
    current = makePiece(next);
    next = drawFromBag();
    if (collides(current.cells, current.x, current.y)) {
      triggerGameOver();
    }
  }

  function triggerGameOver() {
    gameOver = true;
    started = false;
    sfx.gameOver();
    vibrate([80, 60, 80, 60, 200]);
    updateOverlay();
  }

  function ghostY() {
    let gy = current.y;
    while (!collides(current.cells, current.x, gy + 1)) gy++;
    return gy;
  }

  // ---------- Rendering ----------
  function drawBlock(px, py, size, style) {
    if (style === "ghost") {
      ctx.strokeStyle = COLORS.mid;
      ctx.lineWidth = 1;
      ctx.strokeRect(px + 0.5, py + 0.5, size - 1, size - 1);
      return;
    }
    ctx.fillStyle = COLORS.dark;
    ctx.fillRect(px, py, size, size);
    ctx.fillStyle = COLORS.mid;
    ctx.fillRect(px + 1, py + 1, size - 2, size - 2);
    ctx.fillStyle = COLORS.boardBg;
    ctx.fillRect(px + 1, py + 1, size - 3, 1);
    ctx.fillRect(px + 1, py + 1, 1, size - 3);
  }

  function drawBoard() {
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = COLORS.boardBg;
    ctx.fillRect(BOARD_X, BOARD_Y, COLS * CELL, ROWS * CELL);

    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        if (grid[r][c]) {
          drawBlock(BOARD_X + c * CELL, BOARD_Y + r * CELL, CELL);
        }
      }
    }

    if (!gameOver && started && !paused) {
      const gy = ghostY();
      for (const [cx, cy] of current.cells) {
        const by = gy + cy;
        if (by >= 0) drawBlock(BOARD_X + (current.x + cx) * CELL, BOARD_Y + by * CELL, CELL, "ghost");
      }
      for (const [cx, cy] of current.cells) {
        const by = current.y + cy;
        if (by >= 0) drawBlock(BOARD_X + (current.x + cx) * CELL, BOARD_Y + by * CELL, CELL);
      }
    }

    ctx.strokeStyle = COLORS.dark;
    ctx.lineWidth = 1;
    ctx.strokeRect(BOARD_X + 0.5, BOARD_Y + 0.5, COLS * CELL - 1, ROWS * CELL - 1);

    drawSidebar();
  }

  function pixelText(text, x, y, size, color, align = "left") {
    ctx.fillStyle = color;
    ctx.font = `bold ${size}px "Courier New", monospace`;
    ctx.textAlign = align;
    ctx.textBaseline = "top";
    ctx.fillText(text, x, y);
  }

  function drawSidebar() {
    const x = SIDE_X;
    pixelText("NEXT", x, BOARD_Y, 8, COLORS.dark);

    const pCell = 6;
    const boxX = x + 4;
    const boxY = BOARD_Y + 12;
    ctx.fillStyle = COLORS.boardBg;
    ctx.fillRect(boxX, boxY, pCell * 4, pCell * 4);
    ctx.strokeStyle = COLORS.dark;
    ctx.strokeRect(boxX + 0.5, boxY + 0.5, pCell * 4 - 1, pCell * 4 - 1);
    if (next) {
      for (const [cx, cy] of PIECES[next].cells) {
        drawBlock(boxX + cx * pCell, boxY + cy * pCell, pCell);
      }
    }

    pixelText("SCORE", x, BOARD_Y + 46, 8, COLORS.dark);
    pixelText(String(score).padStart(6, "0"), x, BOARD_Y + 56, 9, COLORS.dark);

    pixelText("LEVEL", x, BOARD_Y + 78, 8, COLORS.dark);
    pixelText(String(level).padStart(2, "0"), x, BOARD_Y + 88, 9, COLORS.dark);

    pixelText("LINES", x, BOARD_Y + 110, 8, COLORS.dark);
    pixelText(String(lines).padStart(3, "0"), x, BOARD_Y + 120, 9, COLORS.dark);

    pixelText("HI " + String(highScore).padStart(6, "0"), x, BOARD_Y + 148, 7, COLORS.mid);
  }

  // ---------- Overlay ----------
  const overlay = document.getElementById("overlay");
  const overlayTitle = document.getElementById("overlay-title");
  const overlaySub = document.getElementById("overlay-sub");

  function updateOverlay() {
    if (gameOver) {
      overlay.classList.remove("hidden");
      overlayTitle.textContent = "GAME OVER";
      overlaySub.textContent = `SCORE ${score}\nPRESS SELECT TO RETRY`;
    } else if (!started) {
      overlay.classList.remove("hidden");
      overlayTitle.textContent = "TETRIS BOY";
      overlaySub.textContent = "PRESS START\nTO BEGIN";
    } else if (paused) {
      overlay.classList.remove("hidden");
      overlayTitle.textContent = "PAUSED";
      overlaySub.textContent = "PRESS START\nTO RESUME";
    } else {
      overlay.classList.add("hidden");
    }
  }

  // ---------- Game loop ----------
  function tick(time) {
    rafId = requestAnimationFrame(tick);
    if (lastTime == null) lastTime = time;
    const delta = time - lastTime;
    lastTime = time;

    if (started && !paused && !gameOver) {
      dropAccum += delta;
      const interval = softDropping ? Math.max(30, dropInterval / 12) : dropInterval;
      if (dropAccum >= interval) {
        dropAccum = 0;
        if (!tryMove(0, 1)) {
          lockPiece();
        } else if (softDropping) {
          score += 1;
        }
      }
    }
    drawBoard();
  }

  // ---------- Actions ----------
  function doStart() {
    ensureAudio();
    if (gameOver) {
      resetGame();
      started = true;
      updateOverlay();
      return;
    }
    if (!started) {
      started = true;
      paused = false;
    } else {
      paused = !paused;
    }
    updateOverlay();
  }

  function doSelect() {
    ensureAudio();
    resetGame();
    updateOverlay();
  }

  function withGuard(fn) {
    return () => {
      if (!started || paused || gameOver) return;
      fn();
    };
  }

  const actions = {
    left: withGuard(() => { if (tryMove(-1, 0)) sfx.move(); }),
    right: withGuard(() => { if (tryMove(1, 0)) sfx.move(); }),
    down: withGuard(() => {}),
    rotateCW: withGuard(() => tryRotate(true)),
    rotateCCW: withGuard(() => tryRotate(false)),
    hardDrop: withGuard(() => {
      let dist = 0;
      while (tryMove(0, 1)) dist++;
      score += dist * 2;
      sfx.hardDrop();
      vibrate(15);
      lockPiece();
      dropAccum = 0;
    }),
    start: doStart,
    select: doSelect,
  };

  // ---------- Input handling ----------
  const REPEAT_DELAY = 170;
  const REPEAT_RATE = 50;
  const activeTimers = new Map();

  function pressAction(action, el) {
    if (action === "down") {
      softDropping = true;
      return;
    }
    if (action === "left" || action === "right") {
      actions[action]();
      const id = setTimeout(function repeat() {
        actions[action]();
        activeTimers.set(action, setTimeout(repeat, REPEAT_RATE));
      }, REPEAT_DELAY);
      activeTimers.set(action, id);
      return;
    }
    actions[action] && actions[action]();
  }

  function releaseAction(action) {
    if (action === "down") {
      softDropping = false;
      return;
    }
    if (activeTimers.has(action)) {
      clearTimeout(activeTimers.get(action));
      activeTimers.delete(action);
    }
  }

  document.querySelectorAll("[data-action]").forEach((el) => {
    const action = el.dataset.action;
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      el.setPointerCapture && el.setPointerCapture(e.pointerId);
      pressAction(action, el);
    });
    ["pointerup", "pointercancel", "pointerleave", "pointerout"].forEach((evt) => {
      el.addEventListener(evt, (e) => {
        e.preventDefault();
        releaseAction(action);
      });
    });
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  });

  muteBtn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    muted = !muted;
    localStorage.setItem("tetrisboy-muted", muted ? "1" : "0");
    muteBtn.textContent = muted ? "🔇" : "🔊";
  });

  const KEY_MAP = {
    ArrowLeft: "left",
    ArrowRight: "right",
    ArrowDown: "down",
    ArrowUp: "rotateCW",
    KeyX: "rotateCW",
    KeyZ: "rotateCCW",
    Space: "hardDrop",
    Enter: "start",
    KeyP: "start",
    ShiftLeft: "select",
    ShiftRight: "select",
    KeyR: "select",
  };
  const heldKeys = new Set();

  window.addEventListener("keydown", (e) => {
    const action = KEY_MAP[e.code];
    if (!action) return;
    e.preventDefault();
    if (heldKeys.has(e.code)) return;
    heldKeys.add(e.code);
    pressAction(action);
  });

  window.addEventListener("keyup", (e) => {
    const action = KEY_MAP[e.code];
    if (!action) return;
    heldKeys.delete(e.code);
    releaseAction(action);
  });

  // ---------- Boot ----------
  resetGame();
  rafId = requestAnimationFrame(tick);
})();
