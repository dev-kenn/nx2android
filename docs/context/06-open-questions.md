# nx2android - Open Questions & TODOs

Issues worth exploring before committing to code changes. Based on README, ARCHITECTURE.md, PORT_CHECKLIST.md and RESEARCH.md.

---

## Architecture & Design

- **Shared font system.** `--shared-font` (`DM_SHARED_FONT`) loads a single `.ttf` per game into the data pack. The Porter's own title panel shows only ASCII (`???`). When no shared font is provided, button icons render as `?`. Should this be auto-configured from game locale strings?

- **External display support.** Experimental: `--external-display` moves the game to a connected display while phone becomes a gamepad. Requires `javac` and Android SDK with build-tools (`ANDROID_HOME`). Varies by device/game. Is this stable enough for production builds?

- **Multithread replay toggle.** Tick **Multithread replay** on Port tab (`--mt-replay`). Vulkan commands recorded on separate thread. Stays on until game ported again without it. Should this be per-game default in android.tsv?

## Runtime & Engine (nxnative)

- **Adreno zero-copy memory pools.** Core innovation: `AHardwareBuffer` → `mmap(MAP_FIXED)` + VkBuffer import. Guest pointer is GPU memory, CPU-cached and coherent (~15-17 ms per 64 MB). Verified with no wrong words in 2 x 64 MB on Adreno. How to handle non-Adreno (Xclipse, Mali)?

- **BCn texture support.** Game textures must be readable by the device GPU. Adreno and Xclipse supported; Mali/PowerVR not yet. This limits target devices. When will Turnip/Mesa fully support BC4-7?

- **Shader bundle format (.dmsv).** Built at port time by `shader_vk.py` (SPIR-V to zstd-compressed). Decompressed at runtime by `gfx_vk_shader.c`. Version 1-2 conversion supported. Should we add compression levels or lazy loading for large bundles?

- **Oodle decompression (`hle_oodle.c`).** Required for UE5 games' packed data. The game's own decoder runs on device. What other packing formats are encountered?

## Port Pipeline (porter)

- **NSZ/XCZ decompression.** Decompressed during port into `tmp/` build folder, deleted after extraction. Requires ~2x free space as input. Is there a way to stream directly from compressed format?

- **FPSLocker integration.** Fetches from masagrator's Warehouse (`fpslocker.py`). Converts raw YAML to fpslock.tsv + CUTS patches. How reliable is the upstream data source?

- **Memory headroom (`--alias-headroom`).** Games crashing with "AllocateAddressRegion refused (0x1803)" need more address space. Currently a manual option on Port tab. Should this be auto-calculated from game memory layout?

## Game Profiles

- **41 games not yet ported on Android.** Upstream profiles in seedds/nxnative serve as reference. Priority order for which games to port next?

- **33 of 99 total profiled** (per PORT_CHECKLIST.md). Many are "profile here" (have game.tsv but no android.tsv) or upstream-only (iOS). Some are iPhone-only via Apple Arcade/Netflix.

- **Unpacking** appears as playable on this port despite having an official Android release. Unusual case worth documenting.

- **Lonely Mountains: Downhill** runs with DM_VK_MT_REPLAY=1 and custom PurpleVK driver (git-62ac221a33). Other games may need similar non-standard configurations?

## Testing & QA

- **Soak testing.** 20-minute tests record frame drops, memory footprint, CPU/GPU timing. How many games have been fully soaked vs. just smoke-tested?

- **Performance benchmarks.** No automated framework yet. Manual per-game profiling on each device variant. Should we add CI-based perf regression detection?

- **Save management testing.** Save export/import works via `saves_android.c` and internal storage. Has cross-device save compatibility been tested?

## Build & Release

- **PyInstaller bundle.** Produces distributable zip with Porter + committed nxnative/ source + build.gradle. How stable is the build process across Python versions?

- **Test suite coverage.** Unit tests cover architecture rules, ADB push, Vulkan memory, shader formats. What gaps remain?

---

## Recent Changes Worth Knowing

- **Lonely Mountains: Downhill** uses `DM_VK_MT_REPLAY=1` (multithread replay) and custom PurpleVK driver. This is the most recent tested port (2026-11-05).

- **Metroid Dread** update 2.1.0 now playable with fix for dark area blackness (image-based light cube maps). Core bug was in `hle_nvn.c nvnTextureInitialize` — CPU_NO_ACCESS textures not packaged with memory layout.

- **Port check:** 33 of 99 total games have profiles in PORT_CHECKLIST.md. ~41 started on Android, but many still WIP or experimental.

---

*Sources: README.md, ARCHITECTURE.md, DEVELOPMENT_GUIDE.md, PORT_CHECKLIST.md, RESEARCH.md.*
