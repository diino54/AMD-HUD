# Configuration reference

`config.json` is live user data next to `hud.py`. Read using UTF-8 with optional BOM;
save using UTF-8, two-space indentation, and a trailing newline. The application
resolves this path from its source directory. Settings edits remain buffered until
**Save and apply** or Ctrl+S. A running HUD reloads saved config; external edits need
a restart or explicit reload signal.

The live file is excluded from GitHub. On a fresh checkout, copy the published
`config.example.json` to `config.json` before launching. The example has no personal
font or game paths; an empty AMD profiles path uses the OS-resolved default.
Do not copy the example over an existing user's configuration.

## Defaults, required keys, and validation

This is a reference for the implementation, not a complete schema enforced uniformly
at every entry point. `hud.validate_config()` validates runtime fields and fills some
defaults. `settings_store.write_config()` additionally checks position and palette.
Settings starts from a deep copy and preserves unexposed/unknown keys.

**Required** below means the shipped load/render path expects the field. Missing
required keys are not restored by merging a complete default configuration. The
current saved values are not the same thing as defaults and must not be reset.

### Runtime and visibility

| Key | Default if omitted | Meaning and bounds |
| --- | --- | --- |
| `gpu_index` | Required | Nonnegative integer GPU index; actual GPU count checked during monitor startup; UI range 0–15 |
| `refresh_ms` | Required | Metric text interval, 250–10000 ms; UI step 250 ms |
| `x`, `y` | Required | Screen pixel position; saving requires integers from -20000 to 20000 |
| `click_through` | Required | Pass mouse input through the text window; intended JSON boolean |
| `games_only` | `true` | Show over a recognized foreground game, except preview |
| `amd_profiles_path` | OS local AMD path | Read-only database; empty/missing uses `%LOCALAPPDATA%\AMD\CN\gmdb.blb`; environment variables are expanded |
| `game_executables` | `[]` | Additional full absolute paths; nonempty string list; Windows path normalization used for matching |
| `excluded_executables` | `["wmplayer.exe", "losslessscaling.exe"]` | Case-insensitive executable basenames excluded from recognition |
| `metrics` | Required | Nonempty list of supported metric keys; not a dynamic row layout |

`games_only=false` allows desktop visibility; it does not make PresentMon capture an
arbitrary foreground application. A recognized game PID still supplies the target.
Manual game entries are removable in settings. AMD entries are displayed read-only.

### Background, text, and font

| Key | Default if omitted | Meaning and bounds |
| --- | --- | --- |
| `opacity` | Required | Plain background opacity, 0.2–1.0 |
| `blur` | Runtime fallback `false` | Enable Windows Acrylic |
| `blur_opacity` | Runtime fallback `0.88` | Acrylic material opacity, 0.2–1.0 |
| `corner_radius` | `16` | Integer radius 0–100 px; zero means square |
| `font_size` | Required | Text size, 8–48; passed to Tk as a font size, not the graph-height pixel setting |
| `font_file` | `""` | TTF/OTF path; empty selects Consolas; environment/user expansion and project-relative paths supported by the font loader |
| `background_color` | Required | Tk color key and background tint, `#RRGGBB` |
| `text_color` | Required | Numeric text, `#RRGGBB` |
| `muted_color` | `#6e6a86` at display | Unavailable-value text color |
| `row_colors` | Rosé Pine row palette | Four label colors in GPU, CPU, RAM, FPS/API order |

The current settings loader displays `blur=true` when that key is absent, whereas
the runtime fallback is false. The shipped config includes the key, so normal usage
does not exercise this legacy sparse-config discrepancy. Do not claim that loading
an incomplete JSON file produces a fully uniform default config.

With translucent Acrylic and nonzero radius, runtime uses native 8 px corners while
preserving the saved radius. `blur=true` and `blur_opacity=1` produce an opaque plain
background with custom corners; the unnecessary Acrylic layer is omitted.

Fonts are referenced, not copied or globally installed. A missing file falls back at
runtime; keep a chosen font at its configured location. Resetting the font in settings
sets an empty string and leaves size unchanged.

### Border and shadow

| Key | Default | Meaning and bounds |
| --- | --- | --- |
| `border_enabled` | `true` | Border enable flag |
| `border_width` | `1` | Integer width, 0–8 px |
| `border_opacity` | `1.0` | Opacity, 0–1 |
| `border_color` | `#403d52` at display | Stroke color |
| `shadow_enabled` | `false` | Shadow enable flag |
| `shadow_x` | `0` | Integer horizontal offset, -100–100 px |
| `shadow_y` | `6` | Integer vertical offset, -100–100 px |
| `shadow_opacity` | `0.35` | Opacity, 0–1 |
| `shadow_color` | `#000000` | Shadow color |
| `shadow_blur` | `16` | Integer blur strength, 0–64 px |

Turning off an effect disables related controls without discarding their values.
Offsets apply to the separate shadow window and do not move HUD text. Percentage
controls display 0–100 (or 20–100 for background), but JSON stores fractions.

### Frametime graph

| Key | Default | Meaning and bounds |
| --- | --- | --- |
| `frametime_graph` | `true` | Enable graph beneath the four metric rows |
| `frametime_graph_height` | `48` | Integer graph height, 24–160 px |
| `frametime_color` | `#ebbcba` | Graph heading and stroke color |

Seven-second history and the approximately 60 Hz animation target are currently code
behavior, not configurable JSON fields. History is `hud.GRAPH_WINDOW_SECONDS`.
`refresh_ms` does not change graph speed or animation cadence. Reveal playback adds
an animation backlog, so the viewport is seven seconds relative to its drawing cursor.
Do not add undocumented speed/range keys and expect them to be used automatically.

### Shared palette

`settings_store.PALETTE` defines **Restore Rosé Pine colors**:

| Field | Color |
| --- | --- |
| Background | `#191724` |
| Text | `#e0def4` |
| Border | `#403d52` |
| Unavailable data | `#6e6a86` |
| Shadow | `#000000` |
| Frametime | `#ebbcba` |
| GPU / CPU / RAM / FPS label | `#9ccfd8` / `#c4a7e7` / `#f6c177` / `#eb6f92` |

Palette restore is buffered and does not reset effect strengths, positions, or fonts.

## Metric keys

| Key | Source / unit |
| --- | --- |
| `usage` | ADLX GPUUsage, percent |
| `temperature` | ADLX GPUTemperature, Celsius |
| `power` | ADLX GPUPower, watts; not necessarily total board power |
| `vram` | ADLX GPUVRAM, MB |
| `clock` | ADLX GPUClockSpeed, MHz |
| `fan` | ADLX GPUFanSpeed, RPM |
| `cpu_usage` | ADLX system CPUUsage, percent |
| `cpu_temperature` | Existing AMD CPU server private adapter, Celsius |
| `ram` | ADLX SystemRAM divided by 1024, displayed GiB |
| `fps` | PresentMon rolling rendered FPS; unavailable in a telemetry-only probe |

The four displayed rows are fixed; `power`, `vram`, `clock`, and `fan` are primarily
available for diagnostic snapshots. If a displayed metric is not requested, it shows
unavailable rather than adding or removing a row.

## Persistence contract and current limits

- The writer checks the loaded file digest before replacement and rejects conflicts.
  Reload saved values before saving again; do not overwrite another editor's changes.
- Validation failures leave the original file intact. Temporary save files are cleaned.
- This is not a JSON Schema validator: some legacy fields have range checks without
  strict type checks, and some flags/colors are validated only by the save path or Tk.
  Prefer valid JSON booleans, numeric values, and `#RRGGBB` colors.
- Do not commit personal path changes as documentation examples. Add a game using
  a path such as `D:\Games\Example\Game.exe`; JSON requires escaped backslashes:

```json
"game_executables": ["D:\\Games\\Example\\Game.exe"]
```

This fragment is not a standalone config. Copying it over the entire live file would
remove required settings.
