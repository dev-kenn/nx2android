# Frame Generation Plan (LSFG-style)

**Branch:** `feat/framegen-lsfg`  
**Status:** Phase 2 under way. Done: extractor (202 DXBC blobs, stage detection), CLI/pipeline flags, stage 2: compute pass with frame history (test blend shader, not yet on a device). Not done: DXBC to SPIR-V, dispatch sequence, compute passes.  
**User DLL:** `Lossless.dll` in the repo root (git-ignored, never committed)

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

### 1.2 DLL Analysis (Lossless.dll), verified 2026-11-09

| Property | Value |
|---|---|
| Format | PE32+ executable (DLL), x86-64 |
| Size | 7,521,280 bytes |
| DXBC blobs | 202, all unique, 5,121,772 bytes together |
| Container | Standard, unobfuscated DXBC (version 1 at +0x14, totalSize at +0x18, chunk table at +0x20) |
| Stage | Every blob's SHEX version token decodes to program type 5 (compute), SM 5.0 |

The DLL is **not** packed or obfuscated: the blobs are found by scanning for `DXBC` and checking the container header (`porter/lsfg_extract.py`). The earlier claim of a packed PE with garbled sections was wrong.

**DXBC to SPIR-V (verified 2026-11-09):** `dxc` cannot read compiled DXBC, so the porter uses `vkd3d-compiler -x dxbc-tpf -b spirv-binary` (vkd3d-shader, built from source on Windows; set `LSFG_VKD3D_COMPILER` to its path). All 202 blobs convert and all 202 pass `spirv-val --target-env vulkan1.1`. Reflection shows 75 distinct binding signatures: binding 0 is usually a constant buffer, the rest are textures or storage images, all in descriptor set 0. Local sizes: 154 shaders 8x8, 31 16x16, 7 64x1, 6 32x32, 2 128x1, 2 256x1. Still unknown, and not in the bytecode: the dispatch order, what each binding holds and how outputs chain. That needs a GPU capture (RenderDoc or PIX) of Lossless Scaling on Windows.

### 1.3 Cost Estimate

**Not measured.** No shader has been run on a phone GPU yet, so there is no timing or memory figure. Whether the 202 compute shaders fit a phone's frame budget is the open go/no-go question. It has to be measured on the device (Magenta) once the shaders run. Until then, treat any "feasible" or "infeasible" claim as a guess.

Known design points: framegen adds at least one frame of latency, and it needs history buffers at the game's resolution (size to be computed from the real shader inputs, not estimated here). If the pack is missing or pipeline creation fails, present normally and log `[vk] framegen: pack not found, presenting normally`.

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
| Dispatch order and bindings of the 202 shaders unknown | **High** | High | Capture Lossless Scaling with RenderDoc or PIX on Windows. |
| Mobile GPU cannot run LSFG shaders at target resolution | **Likely** (mobile VRAM bandwidth limit) | Medium-High | Graceful fallback: disable silently, log line emitted. Offer lower resolution mode. |
| DXBC to SPIR-V conversion fails for some shaders | Medium | Medium | Use `vkd3d-compiler`; check every blob converts and passes `spirv-val`. |
| History buffer memory exceeds device capacity | **Likely** (720p+ games) | Medium | Limit history buffers to 1–2 frames; detect available VRAM; auto-disable if insufficient. |
| Framegen breaks certain game rendering patterns | Low | Low | Per-game whitelist in android.tsv: `framegen_safe=yes/no`. Off by default anyway. |

### 5. Effort Estimate

| Phase | Effort | Notes |
|---|---|---|
| DLL extraction (done) and DXBC to SPIR-V | 1–2 days | Extraction is done; conversion with vkd3d-compiler is pending. |
| Porter CLI + data pack integration | 0.5 day | Straightforward: add flags, env rows, copy files into pack. |
| nxnative framegen module (C/Vulkan) | 3–5 days | Post-process pipeline management follows existing patterns (`rot.*` shaders). |
| Testing & refinement | 2–3 days | Most effort on-device tuning. |
| **Total** | **~8–12 days** | Research-heavy; actual implementation may be less if shaders are easily extractable. |

### 6. Git-Aware File Map

```
porter/
  cli.py                    # + --framegen, --lsfg-dll
  pipeline.py               # + framegen field in Options; call lsfg_extract()
  lsfg_extract.py           # NEW: extraction tool (reads DLL; optional vkd3d-compiler step)

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

### 7. Steps (1-4 done, 5 started at stage 1; the rest open)

1. **Implement `porter lsfg-extract`** — standalone CLI tool that reads Lossless.dll and extracts shaders to `.gamedump/lsfg/<id>/`.
2. **Wire up CLI flags** — `--framegen` enables the feature; `--lsfg-dll <path>` provides the DLL path (defaults to `Lossless.dll` in the game folder).
3. **Add Porter stage** — call extraction in `Port.run()` between `shaders()` and `host()`.
4. **Add `DM_FRAMEGEN=1` env row** — same pattern as `fps_env`.
5. **Implement framegen module** — minimal viable: load shader pack, create swapchain images as history buffers, run one interpolation pass per present.
6. **Integrate into vk_present()** — between the game's final blit and PRESENT_SRC barrier.
7. **Safe fallback** — if shader pack missing or pipeline creation fails, present normally with a log line.
8. **Tests** — pure-Python unit tests for extraction stub and flag plumbing.
9. **Update docs** — add framegen section to ARCHITECTURE.md.




