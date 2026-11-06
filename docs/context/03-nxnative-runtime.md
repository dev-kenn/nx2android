# nx2android — nxnative Runtime (Part 1)

This is the native execution engine, forked from [seedds/nxnative](https://github.com/seedds/nxnative) (MIT). The port added Android-specific code in `dm/android/` alongside the shared core.

---

## Directory structure at a glance

```
nxnative/
├── dm/
│   ├── host/          Shared Horizon OS host (C): every game + both platforms
│   ├── gfx/           Graphics layer: GL / Metal / NVN / Vulkan — shared core
│   ├── tools/         Binary analysis tools: rewriter, shader split, NSO parsing — shared
│   ├── third_party/   vendored libraries: zstd, capstone, lz4, GLSLang, SPIRV-Cross, etc.
│   └── android/       Android runtime (C): Vulkan backend, NativeActivity front-end, build
```

---

## The Host Runtime (`dm/host/`)

The Horizon OS host stands in for the Nintendo Switch kernel and system services. Each port compiles a custom `libdmhost.so` with the game's modules linked in.

### Core files

| File | Purpose |
|---|---|
| `main.c` | Bootstrap: loads modules, initializes SDK runtime (nn::init::Start), enters nnMain. Sets up guest thread, crash handling, time zones, file limits |
| `loader.c` | Module loader: finds and loads NSO modules from RomFS, resolves symbols |
| `hle.c` / `hle.h` | High-Level Emulation base: dispatch table for Horizon syscalls, SDK version detection |
| `dm.h` / `front.h` / `dm_uc.h` | Internal interfaces: game flags, front-end API, undefined behavior tracking |

### Service implementations (HLE — high-level emulation)

| File | Services / Systems |
|---|---|
| `hle_fs.c` | File system abstraction (reads from RomFS on device) |
| `hle_hid.c` | Input: gamepad buttons, sticks, triggers, gyroscope, rumble |
| `hle_touch.c` | Touch screen input (maps to game's touch API) |
| `hle_audio.c` / `hle_audren.c` | Audio playback and device routing |
| `hle_time.c` | System time / calendar conversion |
| `hle_thread.c` | Thread management, scheduling |
| `hle_count.c` | Counters and performance monitoring |
| `hle_net.c` | Network services (minimal) |
| `hle_ro.c` | Read-only data / configuration |
| `hle_oe.c` | Application lifecycle (foreground/background) |
| `hle_offline.c` | Offline mode features |
| `hle_sdk16.c` | Nintendo SDK 16+ layer (shared fonts, etc.) |
| `hle_sf.c` | Save data / file save services |
| `hle_os.c` | OS-level services (memory allocation, string handling) |
| `hle_codec.c` | Codec services (audio/video decoding) |
| `hle_movie.c` / `hle_movie_avc.c` | Movie playback (VP9, AVC) |
| `hle_oodle.c` | Oodle decompression service (UE5 games) |
| `hle_bigstack.c` | Large stack allocations |
| `hle_haptics.c` | Haptic feedback |
| `hle_nvdrv.c` | NVDriver (graphics driver interface) |

---

*Sources: nxnative/dm/host/*, porter/pipeline.py.*


---

## The Vulkan Backend (`dm/android/gfx_vk_*.c`)

Replays Nintendo's NVN graphics on Android's Vulkan driver.

### Core design: AHardwareBuffer zero-copy memory pools

NVN gives the GPU game memory with CPU address = GPU address. The Android port achieves this by:
1. Allocating an `AHardwareBuffer` of the required size
2. Copying current contents to it
3. `mmap(MAP_FIXED)` mapping its dma-buf fd over the guest's allocation region
4. Importing the same AHardwareBuffer as a VkBuffer

Result: the game pointer is GPU memory, CPU-cached and coherent on Adreno (~15-17 ms per 64 MB).

### Core Vulkan files

| File | Purpose |
|---|---|
| `gfx_vk.h` | Vulkan device state, pool management, submission slots header |
| `gfx_vk_core.c` | Device init, memory pools (AHardwareBuffer zero-copy), submissions. Up to 32768 pools |
| `gfx_vk_present.c` | Swapchain management, present timing (vsync). Adaptive frame rate stepping |
| `gfx_vk_dq.c` | Command queue & dispatch. Multi-thread replay (DM_VK_MT_REPLAY). Dirty block tracking |
| `gfx_vk_exec.c` | Execution context: command buffer recording, per-slot state |
| `gfx_vk_shader.c` | Shader bundle decompression at runtime (zstd-decompressed SPIR-V) |
| `gfx_vk_tex.c` | Texture layout (deko3d algorithm), BCn compression |
| `gfx_vk_subgroup.c` | Subgroup operations for SIMD-style GPU code |

### Shader bundle (.dmsv)

Built by `shader_vk.py`: compiles SPIR-V to zstd-compressed form, produces one .dmsv. At runtime, gfx_vk_shader.c decompresses each shader. Version 1-2 conversion supported.

---

## Per-Game Profiles (dm/games/<titleID>/)

Data-driven: no code branches per game. Add TSV files and optionally patches.py to support a game.

### Status values in android.tsv

- `playable` — Tested and working (appears in README.md Games table)
- `wip` / `experimental` — Work in progress or provisional port
- (no android.tsv) — iOS-only, not ported to Android yet

---

*Sources: nxnative/dm/android/\*, porter/pipeline.py.*
