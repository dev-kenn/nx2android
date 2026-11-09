# lsfg_bench

Standalone arm64 Android program that times the converted Lossless LSFG compute shaders (`.spv`) on the phone GPU, to decide whether frame generation is affordable.

```
py devtools/lsfg_bench/build.py [--ndk <NDK dir>]      # -> devtools/lsfg_bench/build/lsfg_bench
py devtools/lsfg_bench/run.py [--spv <dir>] [bench args]  # push + run on R5CTA04NZWN (Magenta)
```

Bench args: `--size WxH` (default 1920x1080), `--runs N` (20), `--warmup N` (3), `--only substr`, `--limit N`, `--top N` (10).
Default spv dir: `.gamedump/LosslessLSFG/spirv/shaders`.

## No manifest needed

The SPIR-V is reflected in C (`OpDecorate` set/binding, `OpTypeImage/Sampler/SampledImage/Struct`, `LocalSize`, push-constant block size), so `manifest.json` from `porter/lsfg_reflect.py` is not read.

## Approximations (numbers are indicative only)

- All resources are zero-filled and never contain real frames; zero data can flatter data-dependent branches and caches.
- Every shader is dispatched `ceil(W/lx) x ceil(H/ly)` groups at the full frame size. Real LSFG runs many passes at reduced resolutions, so shaders may be over- or under-counted.
- Images are WxH (3D: 64^3, arrayed: 4 layers). Storage image formats come from the shader; unknown format uses RGBA8, sampled images use RGBA16F (R32 for int types).
- Buffer sizes come from the reflected struct size; runtime arrays are guessed as W*H dwords; texel buffers are 4 MiB.
- "Total if every shader runs once" is a sum of single dispatches, not a frame budget.
- Each run is timed alone (timestamps around one dispatch, queue idle between runs), so the GPU may be at lower clocks than under sustained load.
