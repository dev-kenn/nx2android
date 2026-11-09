"""Pure-Python SPIR-V reflection for the LSFG compute shaders.

Parses the SPIR-V binary words directly (no spirv-dis) and reports, per shader:
LocalSize, every descriptor binding (set, binding, kind, image dim / sampled
type / format, buffer byte size), the push-constant block size and the
binding count.

CLI: py -m porter.lsfg_reflect <spv_dir> --out <manifest.json>
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

MAGIC = 0x07230203

# Opcodes
OP_ENTRY_POINT = 15
OP_EXECUTION_MODE = 16
OP_TYPE_BOOL = 20
OP_TYPE_INT = 21
OP_TYPE_FLOAT = 22
OP_TYPE_VECTOR = 23
OP_TYPE_MATRIX = 24
OP_TYPE_IMAGE = 25
OP_TYPE_SAMPLER = 26
OP_TYPE_SAMPLED_IMAGE = 27
OP_TYPE_ARRAY = 28
OP_TYPE_RUNTIME_ARRAY = 29
OP_TYPE_STRUCT = 30
OP_TYPE_POINTER = 32
OP_CONSTANT = 43
OP_VARIABLE = 59
OP_DECORATE = 71
OP_MEMBER_DECORATE = 72
OP_EXECUTION_MODE_ID = 331
OP_SPEC_CONSTANT = 50

# Decorations
DEC_BLOCK = 2
DEC_BUFFER_BLOCK = 3
DEC_ARRAY_STRIDE = 6
DEC_MATRIX_STRIDE = 7
DEC_ROW_MAJOR = 4
DEC_BINDING = 33
DEC_DESCRIPTOR_SET = 34
DEC_OFFSET = 35

# Storage classes
SC_UNIFORM_CONSTANT = 0
SC_UNIFORM = 2
SC_PUSH_CONSTANT = 9
SC_STORAGE_BUFFER = 12

EM_LOCAL_SIZE = 17
EM_LOCAL_SIZE_ID = 38

DIMS = {0: "1D", 1: "2D", 2: "3D", 3: "Cube", 4: "Rect", 5: "Buffer", 6: "SubpassData"}

FORMATS = {
    0: "Unknown", 1: "rgba32f", 2: "rgba16f", 3: "r32f", 4: "rgba8",
    5: "rgba8snorm", 6: "rg32f", 7: "rg16f", 8: "r11fg11fb10f", 9: "r16f",
    10: "rgba16", 11: "rgb10a2", 12: "rg16", 13: "rg8", 14: "r16",
    15: "r8", 16: "rgba16snorm", 17: "rg16snorm", 18: "rg8snorm",
    19: "r16snorm", 20: "r8snorm", 21: "rgba32i", 22: "rgba16i",
    23: "rgba8i", 24: "r32i", 25: "rg32i", 26: "rg16i", 27: "rg8i",
    28: "r16i", 29: "r8i", 30: "rgba32ui", 31: "rgba16ui", 32: "rgba8ui",
    33: "r32ui", 34: "rg32ui", 35: "rgb10a2ui", 36: "rg16ui", 37: "rg8ui",
    38: "r16ui", 39: "r8ui",
}


def _words(data: bytes) -> list[int]:
    if len(data) % 4 or len(data) < 20:
        raise ValueError("not a SPIR-V binary (bad length)")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == MAGIC:
        endian = "<"
    elif struct.unpack_from(">I", data, 0)[0] == MAGIC:
        endian = ">"
    else:
        raise ValueError("bad SPIR-V magic")
    return list(struct.unpack(f"{endian}{len(data) // 4}I", data))


def reflect_bytes(data: bytes) -> dict:
    """Reflect one SPIR-V module given as bytes."""
    w = _words(data)
    types: dict[int, tuple] = {}
    consts: dict[int, int] = {}
    decos: dict[int, dict[int, list[int]]] = {}
    mdecos: dict[tuple[int, int], dict[int, list[int]]] = {}
    variables: list[tuple[int, int, int]] = []  # (id, ptr type, storage class)
    local_size = None
    local_size_ids = None

    i = 5
    while i < len(w):
        wc = w[i] >> 16
        op = w[i] & 0xFFFF
        if wc == 0:
            raise ValueError("zero word count")
        a = w[i + 1:i + wc]
        if op == OP_EXECUTION_MODE and len(a) >= 5 and a[1] == EM_LOCAL_SIZE:
            local_size = (a[2], a[3], a[4])
        elif op == OP_EXECUTION_MODE_ID and len(a) >= 5 and a[1] == EM_LOCAL_SIZE_ID:
            local_size_ids = (a[2], a[3], a[4])
        elif op == OP_TYPE_BOOL:
            types[a[0]] = ("bool",)
        elif op == OP_TYPE_INT:
            types[a[0]] = ("int", a[1], a[2])
        elif op == OP_TYPE_FLOAT:
            types[a[0]] = ("float", a[1])
        elif op == OP_TYPE_VECTOR:
            types[a[0]] = ("vector", a[1], a[2])
        elif op == OP_TYPE_MATRIX:
            types[a[0]] = ("matrix", a[1], a[2])
        elif op == OP_TYPE_IMAGE:
            types[a[0]] = ("image", a[1], a[2], a[3], a[4], a[5], a[6], a[7])
        elif op == OP_TYPE_SAMPLER:
            types[a[0]] = ("sampler",)
        elif op == OP_TYPE_SAMPLED_IMAGE:
            types[a[0]] = ("sampledimage", a[1])
        elif op == OP_TYPE_ARRAY:
            types[a[0]] = ("array", a[1], a[2])
        elif op == OP_TYPE_RUNTIME_ARRAY:
            types[a[0]] = ("rtarray", a[1])
        elif op == OP_TYPE_STRUCT:
            types[a[0]] = ("struct", list(a[1:]))
        elif op == OP_TYPE_POINTER:
            types[a[0]] = ("pointer", a[1], a[2])
        elif op == OP_CONSTANT and len(a) >= 3:
            consts[a[1]] = a[2]
        elif op == OP_SPEC_CONSTANT and len(a) >= 3:
            consts.setdefault(a[1], a[2])
        elif op == OP_VARIABLE:
            variables.append((a[1], a[0], a[2]))
        elif op == OP_DECORATE:
            decos.setdefault(a[0], {})[a[1]] = list(a[2:])
        elif op == OP_MEMBER_DECORATE:
            mdecos.setdefault((a[0], a[1]), {})[a[2]] = list(a[3:])
        i += wc

    if local_size is None and local_size_ids is not None:
        local_size = tuple(consts.get(x, 0) for x in local_size_ids)

    def dec_val(tid: int, d: int):
        v = decos.get(tid, {}).get(d)
        return v[0] if v else None

    def size_of(tid: int) -> tuple[int, bool]:
        """Return (byte size, has_runtime_array_tail)."""
        t = types[tid]
        k = t[0]
        if k == "bool":
            return 4, False
        if k == "int":
            return t[1] // 8, False
        if k == "float":
            return t[1] // 8, False
        if k == "vector":
            return size_of(t[1])[0] * t[2], False
        if k == "matrix":
            stride = None
            col = size_of(t[1])[0]
            return (stride or col) * t[2], False
        if k == "array":
            stride = dec_val(tid, DEC_ARRAY_STRIDE) or size_of(t[1])[0]
            return stride * consts.get(t[2], 0), False
        if k == "rtarray":
            return 0, True
        if k == "struct":
            end = 0
            rt = False
            for idx, m in enumerate(t[1]):
                off = mdecos.get((tid, idx), {}).get(DEC_OFFSET, [0])[0]
                mt = types[m]
                if mt[0] == "matrix":
                    ms = mdecos.get((tid, idx), {}).get(DEC_MATRIX_STRIDE, [None])[0]
                    col = size_of(mt[1])[0]
                    sz = (ms or col) * mt[2]
                    r = False
                else:
                    sz, r = size_of(m)
                rt = rt or r
                end = max(end, off + sz)
            return end, rt
        return 0, False

    bindings = []
    push_size = 0
    for vid, ptype, sc in variables:
        p = types.get(ptype)
        if not p or p[0] != "pointer":
            continue
        t = p[2]
        count = 1
        while types[t][0] in ("array", "rtarray"):
            if types[t][0] == "array":
                count *= max(consts.get(types[t][2], 1), 1)
            t = types[t][1]
        tt = types[t]
        if sc == SC_PUSH_CONSTANT:
            push_size = max(push_size, size_of(t)[0])
            continue
        if sc not in (SC_UNIFORM_CONSTANT, SC_UNIFORM, SC_STORAGE_BUFFER):
            continue
        b = dec_val(vid, DEC_BINDING)
        if b is None:
            continue
        entry = {"set": dec_val(vid, DEC_DESCRIPTOR_SET) or 0, "binding": b}
        if count > 1:
            entry["count"] = count
        if tt[0] == "image":
            _, st, dim, _depth, arrayed, ms, sampled, fmt = tt
            stype = types.get(st, ("?",))
            if dim == 5:
                kind = "texel-buffer"
            elif sampled == 2:
                kind = "storage-image"
            else:
                kind = "sampled-image"
            entry.update(
                kind=kind,
                dim=DIMS.get(dim, str(dim)),
                sampled_type=_type_name(stype),
                format=FORMATS.get(fmt, str(fmt)),
                arrayed=bool(arrayed),
                multisampled=bool(ms),
            )
            if dim == 5:
                entry["texel_buffer_storage"] = sampled == 2
        elif tt[0] == "sampledimage":
            it = types[tt[1]]
            entry.update(
                kind="combined-image-sampler",
                dim=DIMS.get(it[2], str(it[2])),
                sampled_type=_type_name(types.get(it[1], ("?",))),
                format=FORMATS.get(it[7], str(it[7])),
            )
        elif tt[0] == "sampler":
            entry["kind"] = "sampler"
        elif tt[0] == "struct":
            size, rt = size_of(t)
            if sc == SC_STORAGE_BUFFER or dec_val(t, DEC_BUFFER_BLOCK) is not None or (
                sc == SC_UNIFORM and DEC_BUFFER_BLOCK in decos.get(t, {})
            ):
                entry["kind"] = "storage-buffer"
            else:
                entry["kind"] = "uniform-buffer"
            entry["size"] = size
            if rt:
                entry["runtime_array"] = True
        else:
            continue
        bindings.append(entry)

    bindings.sort(key=lambda e: (e["set"], e["binding"]))
    return {
        "local_size": list(local_size) if local_size else None,
        "bindings": bindings,
        "binding_count": len(bindings),
        "push_constant_size": push_size,
    }


def _type_name(t: tuple) -> str:
    if t[0] == "float":
        return f"f{t[1]}"
    if t[0] == "int":
        return f"{'i' if t[2] else 'u'}{t[1]}"
    return t[0]


def reflect_file(path) -> dict:
    return reflect_bytes(Path(path).read_bytes())


def signature(r: dict) -> str:
    """Stable string for the descriptor layout + push size (not local size)."""
    parts = []
    for b in r["bindings"]:
        parts.append(
            f"{b['set']}.{b['binding']}:{b['kind']}"
            + (f":{b['dim']}:{b['format']}" if "dim" in b else "")
            + (f":{b['size']}" if "size" in b else "")
            + (f"x{b['count']}" if "count" in b else "")
        )
    return "|".join(parts) + f"|pc{r['push_constant_size']}"


def reflect_dir(spv_dir) -> dict:
    """Reflect every .spv in spv_dir. Returns {"shaders": {stem: info}, "summary": {...}}."""
    shaders = {}
    for p in sorted(Path(spv_dir).glob("*.spv")):
        shaders[p.stem] = reflect_file(p)
    sigs = {signature(r) for r in shaders.values()}
    kinds = Counter(b["kind"] for r in shaders.values() for b in r["bindings"])
    formats = Counter(
        b["format"] for r in shaders.values() for b in r["bindings"] if b["kind"] == "storage-image"
    )
    ubo_sizes = Counter(
        b["size"] for r in shaders.values() for b in r["bindings"] if b["kind"] == "uniform-buffer"
    )
    summary = {
        "shader_count": len(shaders),
        "distinct_binding_signatures": len(sigs),
        "kind_histogram": dict(kinds),
        "storage_image_formats": dict(formats),
        "uniform_buffer_sizes": {str(k): v for k, v in sorted(ubo_sizes.items())},
        "local_sizes": dict(Counter(str(r["local_size"]) for r in shaders.values())),
        "push_constant_sizes": dict(Counter(str(r["push_constant_size"]) for r in shaders.values())),
        "binding_count_histogram": dict(
            sorted(Counter(str(r["binding_count"]) for r in shaders.values()).items())
        ),
    }
    return {"summary": summary, "shaders": shaders}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reflect LSFG SPIR-V shaders")
    ap.add_argument("spv_dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    manifest = reflect_dir(args.spv_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
