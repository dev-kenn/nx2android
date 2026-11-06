# nx2android — Project Overview

**What it is:** A toolchain that ports Nintendo Switch games to Android. The game's own ARM64 code runs natively on the device, with Nintendo's Horizon OS stood in for by a host runtime and NVN graphics replayed on Vulkan.

**End-to-end flow:**
```
Input:  NSP / NSZ / XCI / XCZ (Switch game files) + prod.keys (from your own Switch)
   │
   ▼
 porter pipeline: extract → rewrite code → translate shaders → build host runtime → package APK → [install on device via adb]
   │
   ▼
 Output: <Game>.apk  +  <Game>-data/ (game files, Vulkan shader bundle, env.txt switches)
   │
   ▼
 Install on Android device → play the game natively
```

**Ends with:** An APK and data pack installed on your phone or a connected Android tablet.

---

## Goals

- Run your own dumped Switch games on Android hardware (Snapdragon phones/tablets) at native speed.
- Support as many NVN-rendering games as possible through a data-driven profile system — no per-game C code changes.
- Provide an optional GUI for the port pipeline, with save import/export and settings management from the device.

## Non-goals

- Distributing game files or keys (bring your own dumps).
- Emulating non-Switch platforms (this is Switch → Android only).
- Building or distributing commercial APKs (the tool generates APKs from user-owned dumps).
- Supporting Mali or PowerVR GPU hardware (BC-compressed textures not universally supported).

## Who it is for

Players who own Nintendo Switch games and want to run them on Android devices. Specifically: Snapdragon-based devices with Adreno GPUs (e.g. Lenovo Legion Y700, Retroid Pocket 6) that support BCn texture compression in hardware.

---

## Tech stack

| Layer | Technology |
|---|---|
| **Port pipeline** | Python 3.11+ (`porter/`): extracts NSP/XCI, rewrites ARM64 binaries, translates Maxwell shaders to SPIR-V/Metal, builds the C host runtime with NDK |
| **Runtime (C)** | `nxnative/dm/`: Horizon OS host (`hle_*.c`), NVN-on-Vulkan backend (`gfx_vk_*.c`), Android NativeActivity front-end (`front_android.c`), audio/haptics/input |
| **GUI** | PySide6 (Qt6) desktop app (`gui/`): four tabs — Port, Setup, Games, Saves |
| **Shader translation** | Ryujinx's Vulkan shader translator (C#/SPIR-V → SPIR-V → Metal Shading Language) |
| **Build / packaging** | NDK r27c (clang), .NET SDK 10 (for `nx_extract` and shader tools), PyInstaller (bundle packaging) |
| **Installation** | ADB (Android platform-tools), optional Mesa Turnip bundled driver |

---

## Repo map (top-level folders)

| Folder | One-liner |
|---|---|
| `porter/` | The headless port pipeline: CLI and Python modules that transform game dumps into an APK + data pack |
| `gui/` | PySide6 desktop app wrapping the porter pipeline in a graphical interface |
| `nxnative/` | Our fork of seedds/nxnative: the native execution engine (Horizon host, NVN-on-Metal/Vulkan, Android runtime, game profiles) |
| `packaging/` | PyInstaller bundle builder: produces the distributable zip for players |
| `devtools/` | Scripts for device bring-up (pushing files, screen recording, soak tests, pass traces) |
| `tests/` | Unit tests for architecture rules, porter CLI, ADB, Vulkan memory, shader formats |
| `probes/` | First on-device feasibility probes (C code: CPU probe, Vulkan zero-copy test) |
| `docs/` | Project documentation (ARCHITECTURE, DEVELOPMENT_GUIDE, PORT_CHECKLIST, PORT_STATUS) |
| `.claude/skills/` | Agent skills for game porting workflows (`nx2android-dev`, `switch-android-port`) |

---

*Sources: README.md, ARCHITECTURE.md, DEVELOPMENT_GUIDE.md, RESEARCH.md.*
