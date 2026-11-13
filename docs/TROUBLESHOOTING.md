# Troubleshooting

Use the project's venv and preserve the user's saved configuration and unsaved form
edits. Start with the symptom and a read-only diagnostic; do not reset settings,
install another monitor, or kill unrelated processes as a general repair strategy.
Commands and test scope are in [DEVELOPMENT.md](DEVELOPMENT.md).

## HUD does not appear

1. Check the running state in settings and `hud-error.log` if settings started it.
2. Verify the foreground executable is a recognized full path, not merely the same
   filename. Use `hud.py --probe-game` with awareness that the diagnostic console
   itself can be foreground.
3. Check **Games** for AMD/manual entries; add the actual game executable if needed.
   Launchers and excluded profiles are intentionally filtered.
4. Check `games_only`, manual hide via Ctrl+Alt+F10, and whether the HUD position is
   on a connected monitor. Preserve negative coordinates used by valid monitor layouts.
5. **Preview 10 s** can test saved appearance outside a game after the HUD is started.

Missing/unreadable AMD profiles keep automatic recognition empty; valid manual
paths still work. Do not edit AMD's database to repair this application.
Fullscreen labels do not establish whether a game bypasses desktop composition.
The HUD restores its topmost position while visible, including after display-mode
changes. Windows-composited fullscreen may display it; legacy exclusive paths
cannot. Do not disable HDR or change the game's mode as an automatic workaround.
STALKER 2 fullscreen with HDR has not yet been verified in-game for this change.

## Shortcut error / Win32 error 1409

The global Ctrl+Alt+F10 or Ctrl+Alt+F11 combination is already registered. Check for
another HUD instance, another copy in a different directory, or another application
using it. Same-directory instances are blocked by a mutex, but other project copies
can still conflict on global hotkeys. Stop only the identified owner through its
normal controls; do not kill all Python processes or assume AMD is necessarily at fault.

## Brief black screen, focus loss, or desktop flash on show

The previous Tk mapping/raising path could activate the HUD. Current protection has
two parts: a thread-local activation veto installed before Tk's first native wrapper,
and non-activating native client/wrapper mapping. Backdrop windows also use no-activate
styles and `SetWindowPos` flags.

Check both parts when changing window setup. Merely adding `WS_EX_NOACTIVATE` after
wrapper creation is not enough to prevent its initial activation. Do not fix this
by immediately forcing focus back to the game; that can still trigger a mode switch.
Record whether the HUD actually became foreground and distinguish a game/driver
presentation change from application focus theft. Desktop tests do not settle every
game's fullscreen behavior.

## Black rectangular background or jagged rounded corners

- Tk uses a color key for text/plot; native layers supply the visible background.
  A mismatched graph raster background can appear as a solid rectangle.
- Acrylic uses a compositor-owned rounded geometry clip. A GDI region can break
  Acrylic transparency and must not be applied to its host window.
- Frame and shadow use premultiplied BGRA and fractional edge coverage. Binary
  clipping or straight-alpha pixels cause jagged/dark edges.
- Custom radii retain host-backdrop blur and tint inside the same rounded clip.
  The radius is never silently replaced with 8 px. Windows/system transparency
  preferences can affect the host-backdrop appearance.
- If Acrylic is rejected, a plain layer is the fallback; check stderr for the reason.

## Frametime line jumps, appears in chunks, or stops

| Symptom | Mechanism to inspect |
| --- | --- |
| Existing peaks rearrange as the graph scrolls | Pixel-relative grouping instead of absolute-time buckets |
| Whole trace stretches when a large old spike leaves | Abrupt vertical-range contraction instead of `GraphScale` |
| Trace changes shape/source on near-tied groups | Swap-chain selection without hysteresis |
| Many frames appear together at one time | CSV receipt timestamps instead of QPC frame timestamps |
| Frame ages are negative or several seconds wrong | Mixed `monotonic()`/QPC clock domains |
| A new complete segment pops into view | Reveal cursor bypassed, or tip not clipped progressively |
| Drawing ends and eventually shows waiting | No advancing delivery within 1.5 seconds or measured frames older than 3 seconds; history is not extrapolated |
| Waiting flashes after a delivery batch or source switch | Treating CSV latency as a stopped stream, or cutting new history at receipt time instead of its measured timestamp |
| Entire trace freezes when delivery stops | Viewport clock incorrectly capped by the last received frame |
| Line flashes while data stays fresh | Reconfiguring the currently displayed Tk photo instead of decoding into the hidden buffer |

History is seven seconds relative to the independent scrolling clock; it is not seven seconds of
guaranteed zero-latency wall-clock data. The cursor can trail incoming events while
revealing a batch. Delivery/ETW latency cannot be eliminated by increasing GUI Hz.
It is intentional that a real new stall expands the vertical range immediately.
That differs from a spurious regrouping jump of unchanged data.

`refresh_ms` controls numeric metrics, not graph animation. The graph targets 60 Hz
and uses straight antialiased segments. No dashed reference line or spline is intended.
Keep min/max based on measured samples; the partially revealed endpoint is not a
new frame measurement. Do not conceal a stall by smoothing its data away.

## FPS or API says N/A / FPS

The base PresentMon counter targets a recognized active game's PID. Desktop preview can show
appearance and GPU/CPU values while FPS remains unavailable. Startup and no samples
within 1.5 seconds are also unavailable conditions. Check the vendored executable,
owned capture session, PID visibility, and current game recognition.

The graph itself can require capture even when `fps` is absent from `metrics`.
Conversely, numeric FPS and its adjacent `1000/FPS` interval update on the slower
metric polling interval. Rendered FPS is not a promise of frame-generation coverage.
`DirectX` means a reported DXGI runtime; it is not a hardcoded DirectX 12 claim.

## LSFG row is missing or unavailable

The row requires FPS text, a recognized foreground game, and visible native LS
output on the same monitor. Running the LS settings application alone is not enough.
LS output is identified by its native `LosslessScaling` window class; a changed
class in a future LS version may require reviewing detection. Do not remove the
LS executable exclusion from game recognition to force desktop visibility.

`LSFG` measures total displayed LS output, not generated-only FPS. It does not
prove that frame generation is enabled: plain scaling uses the same output window.
Startup, missing display events, or data older than 1.5 seconds show N/A. There is
no multiplication of game FPS and no fallback to an invented output rate. Ordinary
FPS and the graph still describe the game; LSFG can legitimately differ.

## CPU temperature says N/A

- The ADLX GPU temperature path is separate from CPU temperature.
- The existing AMD CPU server must be installed, running, accessible, and match the
  accepted executable hash. The HUD does not launch or install that server.
- A driver update can change its binary/private layout and intentionally disable
  the adapter. Review the new build instead of removing the compatibility guard.
- The sample must be supported, finite, within the expected range, have a changed
  counter, and be fresh. Cached results older than 2.5 seconds are unavailable.
- The sampling thread can report missing mapping/synchronization objects or mutex
  timeouts. Inspect `CpuTemperature.status` in a controlled diagnostic if needed.

Do not guess a temperature or add a driver as an implicit fallback. The adapter
temporarily requests telemetry and tries to restore that flag; it is not a CPU
tuning API. Architecture details and packet checks are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Settings do not apply / cannot save

Unsaved controls intentionally do not affect the live HUD. Save explicitly; starting
or previewing uses the saved file. A bullet in the title marks pending edits.
On an external-change conflict, reload only after preserving any edits the user wants
to keep. Do not forcibly bypass the loaded digest. Invalid values also leave the
original config unchanged and retain the edit buffer.

Config reload recreates windows and telemetry but does not re-import changed source.
If developing code, gracefully restart the affected process and restore its previous
running state. Do not discard a dirty settings window as part of that restart.

## Font changed unexpectedly / desktop icon looks old

A custom font is a reference to its original TTF/OTF path. If moved, deleted, invalid,
or rejected by GDI, the HUD logs the issue and uses Consolas. Font reset keeps text
size. Settings still uses Noto Sans regardless of HUD font choice.

Rebuild icon assets only after SVG edits, then refresh `Create-DesktopShortcut.cmd`.
Check the shortcut target, working directory, and icon path. Existing windows may
still have assets loaded from their previous process lifetime; restart a clean
settings instance when necessary without losing edits. Do not clear global Windows
icon caches or alter unrelated shortcuts as the first repair attempt.
