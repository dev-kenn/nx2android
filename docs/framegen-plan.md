# Frame Generation Plan (LSFG-style)

**Branch:** `feat/framegen-lsfg`  
**Status:** Phase 1 — Research complete. Awaiting "go".  
**User DLL:** `Lossless.dll` in the project root directory (never committed)

---

## 1. Findings from Research

### 1.1 Swapchain Present Path (`nxnative/dm/android/gfx_vk_present.c`)

The single per-frame-present function is `vk_present()`. For window mode, the sequence is:

```
vk_present(tex_t *game_tex, double period, int crop[4])
  → present_window(game_tex, crop, period, ticket)
    → vkCmdBeginCommandBuffer(cb)
    → transition game texture to GENERAL
    → (optional) blit game texture into intermediate buffer
    → overlay_draw()          // on-screen gamepad / pause menu
    → barrier(g_simg[idx], ..., VK_IMAGE_LAYOUT_PRESENT_SRC_KHR)
    → vkEndCommandBuffer(cb)
    → vkQueueSubmit(submit)
    → vkQueuePresentKHR(present)
```

**Hook point:** Insert the LSFG post-process **between** the last `barrier(...PRESENT_SRC_KHR)` and `vkEndCommandBuffer`. This is exactly where the rotation pre-transform (`rot.*` shaders from commit `f7a3371`) hooks in — it renders to `g_rot.img` then copies (with a quarter-turn) into the swapchain image. The framegen pass follows the same pattern: render into a temporary image, blit to the swapchain, barrier to `PRESENT_SRC_KHR`.

**Swapchain recreation triggers:**
- `dm_front_window()` returns NULL or changes (commit `c41f572`)
- Window size changes (`swap_destroy()` called at line ~164)
- `VK_ERROR_OUT_OF_DATE_KHR` or `VK_SUBOPTIMAL_KHR` with panel rotation change

Any framegen resources must be destroyed and recreated alongside the swapchain.

### 1.3 DLL Analysis (Lossless.dll)

| Property | Value |
|---|---|
| Format | PE32+ executable (DLL), GUI, x86-64 |
| Size | 5.4 MB |
| DXBC blobs found | 202 compiled shader binaries |
| Shader compiler | Microsoft (R) HLSL Shader Compiler 10.1 |
| Key strings | `lsfg`, `LSFG2`, `LSFG3` (C++ class names `?.?AVLSFG@@`, etc.) |

**What this means:**
- All shaders are compiled DXBC (DirectX 11 shader blobs). None are pre-spirv.
- 202 blobs is substantial — includes the LSFG pipeline, motion estimation, upscaling, and ML inference kernels.
- The DLL is likely packed/obfuscated (section names were garbled in manual parsing), but DXBC resources appear contiguous in section 4.

**Unverified (TBC):** Without `pefile` or a hex editor, exact blob boundaries cannot be confirmed. The lsfg-vk reference ([PancakeTAS/lsfg-vk](https://github.com/PancakeTAS/lsfg-vk)) shows the extraction approach:

> Extract DXBC blobs → transpile to GLSL via `dxcompiler` (libshaderc) or `dxc` → compile to SPIR-V. The project maintains a table mapping which shader handles which pipeline stage (input, motion vectors, history buffer management, ML interpolation, output merge).

### 1.5 Cost Estimate

| Metric | Estimate | Notes |
|---|---|---|
| **GPU compute for one interpolated frame** | 20–80 ms on Adreno 735 / Apple A16 | ML inference + motion vectors + history buffer management. Depends heavily on resolution and model size. |
| **Memory: history buffer (3 frames, 1440p, RGBA16F)** | ~256 MB | 3 back+history x 2 channels x 1440x2560 x 4 bytes per float16. |
| **Added latency** | +1–2 frames | The generated frame itself introduces one additional pipeline stage. |
| **Feasibility on mobile GPU** | **Likely infeasible for full 3D games** at target resolution | LSFG-style neural frame generation requires ML inference kernels (matrix multiply) that modern Adreno/Mali GPUs support via FP16, but memory bandwidth at 1440p is the bottleneck. May work at 720p/900p with aggressive downscaling. |
| **Best use case** | 30→60 fps for 2D / menu-driven games | Games whose base frame rate is 30 fps and benefit from interpolation to 60. Simple motion (menus, platformers) interpolates better than complex 3D. |
| **Fallback** | Present without interpolation (game runs at native frame rate) | If shader pack missing or pipeline creation fails. Log: `[vk] framegen: pack not found, presenting normally`. |

### 2. Proposed Architecture

#### 2.3 Runtime Flow (gfx_vk_present.c)

When `DM_FRAMEGEN=1`:

```c
// In vk_present() or present_window()
static int g_framegen_on = -1;  // lazy init
static VkDescriptorPool g_framegen_pool;  
static framegen_state_t g_fg;     // loaded at first enable

if (g_framegen_on < 0) {
    const char *env_val = getenv("DM_FRAMEGEN");
    g_framegen_on = env_val && atoi(env_val);
}

if (g_framegen_on && !g_fg.loaded) {
    if (!framegen_load_pack("/sdcard/.../files/lsfg/manifest.json")) {
        LOG("[vk] framegen: pack not found, presenting normally");
        g_framegen_on = 0;  // disable for remainder of session
    }
}

if (g_framegen_on) {
    framegen_present(&g_fg, game_tex, swapchain_image);
    // Replaces normal present_blit with an interpolated one.
    // If it fails mid-frame: cancel submit, fall back to normal present.
}
```

### 3. Test Plan

#### 3.1 Unit Tests (pure Python, no device)

| Test | Scope |
|---|---|
| `test_lsfg_extract_stub()` | Given a synthetic DLL-like file with injected DXBC blobs, verify the extraction tool finds and decodes them. |
| `test_lsfg_pipeline_flags()` | Verify that `Options(framegen=True)` produces correct env rows and Porter.run() calls the extraction step. |
| `test_lsfg_missing_dll()` | With `--framegen` but no `--lsfg-dll`, verify a clear error message (not a crash). |
| `test_lsfg_data_pack_inclusion()` | Verify extracted shaders end up in `<data>/lsfg/` of the built pack. |

#### 3.2 Integration Tests (on-device)

| Test | Scope |
|---|---|
| `doctor` check | Verify `porter doctor` reports framegen DLL not found (if applicable). |
| `framegen_off_by_default` | Port a game without `--framegen`; verify it runs identically to before. |
| `framegen_on_shader_pack_missing` | Port with `--framegen` but no DLL extraction; run on device → present normally + log. |
| `framegen_on_full_pipeline` | Port with shader pack extracted; run game at 30 fps target → see ~60 fps output. |

#### 3.3 Regression Tests (existing games)

**None change.** Frame generation is opt-in and off by default. All existing tests pass unchanged.

### 4. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| DLL packed/obfuscated, DXBC not directly accessible | **High** (section names garbled) | High | May need dynamic instrumentation or a custom PE parser. Try `dxcompiler` on raw bytes. |
| Mobile GPU cannot run LSFG shaders at target resolution | **Likely** (mobile VRAM bandwidth limit) | Medium-High | Graceful fallback: disable silently, log line emitted. Offer lower resolution mode. |
| Shader extraction tool is complex to build | Medium | Medium | Pre-ship an extraction helper binary (build once on Mac, ship in bundle). Or use Python-based DXBC parser + external dxc call. |
| History buffer memory exceeds device capacity | **Likely** (720p+ games) | Medium | Limit history buffers to 1–2 frames; detect available VRAM; auto-disable if insufficient. |
| Framegen breaks certain game rendering patterns | Low | Low | Per-game whitelist in android.tsv: `framegen_safe=yes/no`. Off by default anyway. |

### 5. Effort Estimate

| Phase | Effort | Notes |
|---|---|---|
| DLL analysis & shader extraction tool | 2–4 days | Most uncertain part. Requires handling packed PE format. |
| Porter CLI + data pack integration | 0.5 day | Straightforward: add flags, env rows, copy files into pack. |
| nxnative framegen module (C/Vulkan) | 3–5 days | Post-process pipeline management follows existing patterns (`rot.*` shaders). |
| Testing & refinement | 2–3 days | Most effort on-device tuning. |
| **Total** | **~8–12 days** | Research-heavy; actual implementation may be less if shaders are easily extractable. |

### 6. Git-Aware File Map

```
porter/
  cli.py                    # + --framegen, --lsfg-dll
  pipeline.py               # + framegen field in Options; call lsfg_extract()
  lsfg_extract.py           # NEW: extraction tool (reads DLL, calls dxc)

nxnative/dm/android/
  gfx_vk_present.c          # + DM_FRAMEGEN check; call framegen_present()
  gfx_vk.h                  # + declarations for framegen module
  framegen_vk.c             # NEW: post-process pipeline
  framegen_vk.h             # NEW: public interface

.gamedump/lsfg/<title_id>/  # git-ignored (per CLAUDE.md)
  manifest.json             # shader pack metadata
  shaders/*.spv             # extracted & converted LSFG shaders

tests/
  test_lsfg_extract.py      # NEW: extraction on synthetic stub
  test_lsfg_port_flags.py   # NEW: flag plumbing

docs/
  framegen-plan.md          # this file
  ARCHITECTURE.md           # updated: add framegen section
```

### 7. Next Steps (Phase 2, only after "go")

1. **Implement `porter lsfg-extract`** — standalone CLI tool that reads Lossless.dll and extracts shaders to `.gamedump/lsfg/<id>/`.
2. **Wire up CLI flags** — `--framegen` enables the feature; `--lsfg-dll <path>` provides the DLL path (defaults to `Lossless.dll` in the game folder).
3. **Add Porter stage** — call extraction in `Port.run()` between `shaders()` and `host()`.
4. **Add `DM_FRAMEGEN=1` env row** — same pattern as `fps_env`.
5. **Implement framegen module** — minimal viable: load shader pack, create swapchain images as history buffers, run one interpolation pass per present.
6. **Integrate into vk_present()** — between the game's final blit and PRESENT_SRC barrier.
7. **Safe fallback** — if shader pack missing or pipeline creation fails, present normally with a log line.
8. **Tests** — pure-Python unit tests for extraction stub and flag plumbing.
9. **Update docs** — add framegen section to ARCHITECTURE.md.




