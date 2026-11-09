# LSFG shader pack extractor for nx2android.
# Reads a user-supplied Lossless.dll (PE32+), finds the standard DXBC shader containers
# embedded in it (plain DXBC: checksum at +4, version 1 at +0x14, totalSize at +0x18, chunk
# table at +0x20), and writes each one out as a .dxbc file plus a metadata.json.
#
# Pipeline: Lossless.dll -> .dxbc blobs -> (vkd3d-shader) -> SPIR-V. The DXBC -> SPIR-V step
# is optional here and needs the `vkd3d-compiler` CLI; dxc cannot read compiled DXBC.
# Nothing here compiles or links: only file I/O and the optional external tool.
#
# Design decisions:
# - The blobs are found by scanning for the 'DXBC' magic and validating the container
#   header, not by parsing PE sections. The DLL is not obfuscated.
# - Each blob is named by the first 16 hex digits of its SHA-256 (deduplicates identical blobs).
# - The shader stage comes from the SHEX chunk's version token, never from strings.
import hashlib
import json
import os
import struct
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


DXBC_MAGIC = b'DXBC'


@dataclass
class DxbcInfo:
    """A single DXBC blob found in Lossless.dll."""
    name: str
    size: int
    offset: int
    checksum: str
    version: str
    profile: str = ''


def _read_u32_le(data, off):
    return struct.unpack_from('<I', data, off)[0]


def _find_dxbc_blob(data, start=0):
    """Find next DXBC blob offset."""
    idx = data.find(b'DXBC', start)
    return idx if idx >= 0 else None


_PROGRAM_TYPE_STAGE = {
    0: 'ps',   # pixel shader
    1: 'vs',   # vertex shader
    2: 'gs',   # geometry shader
    3: 'hs',   # hull shader
    4: 'ds',   # domain shader
    5: 'cs',   # compute shader
}


def _read_shader_stage(blob: bytes, chunk_offsets: list[int]) -> str:
    """Locate the SHEX chunk in *blob* and decode its program type.

    Returns one of 'ps', 'vs', 'gs', 'hs', 'ds', 'cs' (lowercase stage name).
    Raises ValueError when no SHEX chunk or a non-standard token is found.

    Known DXBC container layout:
        +0x00: magic "DXBC"       (4 bytes)
        +0x04–0x13: 16-byte checksum
        +0x14: uint32 one (always 1)
        +0x18: uint32 totalSize
        +0x1C: uint32 chunkCount
        +0x20 onward: chunkCount × uint32, each an offset relative to container start.
    Each chunk: 4-byte tag then uint32 size then data.

    SHEX version token (first uint32 of its data):
        bits 16-23 = program type  (0=ps … 5=cs)
        bits 0-3   = minor version, bits 4-7 = major version.
    """
    # DXBC header guarantees chunk list at offset +0x20
    if len(blob) < 0x20 + 4:
        raise ValueError('blob too short for chunk offsets')

    chunk_count = _read_u32_le(blob, 0x1C)
    off_20 = 0x20

    for i in range(chunk_count):
        cpos = _read_u32_le(blob, off_20 + i * 4)

        # Read chunk tag (first 4 bytes of chunk data)
        if cpos + 4 > len(blob):
            continue
        tag = blob[cpos:cpos + 4]
        if tag == b'SHEX':
            token_off = cpos + 8   # skip tag(4) + size(4), first uint32 is the token
            if token_off + 4 > len(blob):
                raise ValueError('SHEX chunk truncated')
            token = _read_u32_le(blob, token_off)
            stage = _PROGRAM_TYPE_STAGE.get((token >> 16) & 0xFF)
            if stage is None:
                raise ValueError(f'SHEX program type invalid (token=0x{token:08X})')
            return stage

    raise ValueError('no SHEX chunk found')


def extract_dll(dll_path, out_dir=None, force=False):
    """Read Lossless.dll, find all DXBC shader blobs, and save them.

    The DLL may be obfuscated/packed. We scan raw memory for 'DXBC' magic markers
    rather than relying on any particular section layout or packer convention.
    """
    out_dir = Path(out_dir) if out_dir else dll_path.with_suffix('') / 'lsfg'
    out_dir.mkdir(parents=True, exist_ok=True)

    dll_bytes = dll_path.read_bytes()
    blobs = []
    seen = set()
    off = 0

    while (off := _find_dxbc_blob(dll_bytes, off)) is not None:
        # Standard DXBC container: magic(4) + checksum(16) + version(4, =1) + totalSize(4) at
        # +0x18 + chunkCount(4) at +0x1C + chunkCount offsets from +0x20.
        if off + 0x20 > len(dll_bytes):
            break
        container_version, size, chunk_count = struct.unpack_from('<III', dll_bytes, off + 0x14)
        end = off + size
        if (container_version != 1 or chunk_count == 0 or chunk_count > 64
                or size < 0x20 + 4 * chunk_count or end > len(dll_bytes)):
            off += 1
            continue

        blob = dll_bytes[off:end]
        checksum = hashlib.sha256(blob).hexdigest()[:16]

        try:
            profile = _read_shader_stage(blob, [])
        except ValueError:
            profile = ''   # not a shader container (no SHEX chunk); leave the stage empty

        if checksum not in seen:   # identical blobs are written once
            seen.add(checksum)
            blobs.append(DxbcInfo(name=f'shad_{checksum[:8]}', size=size, offset=off,
                                  checksum=checksum, version='', profile=profile))
        off = end

    if not blobs:
        print(f'[lsfg] no DXBC shader blobs found in {dll_path.name}', file=sys.stderr)
        _write_lsfgpack(out_dir, [], force=force)
        return []

    print(f'[lsfg] {len(blobs)} DXBC blob(s) found in {dll_path.name} '
          f'({len(dll_bytes):,} bytes DLL)', file=sys.stderr)

    dxbc_dir = out_dir / 'shaders'
    dxbc_dir.mkdir(exist_ok=True)
    for b in blobs:
        p = dxbc_dir / f'{b.checksum}.dxbc'
        if not p.exists() or force:
            p.write_bytes(dll_bytes[b.offset:b.offset + b.size])

    _write_lsfgpack(out_dir, blobs, force=force)
    return blobs


def _try_vkd3d_blob(blob_path, out_spv):
    """Transpile one compiled DXBC (SM4/5, TPF) blob to SPIR-V with the vkd3d-compiler CLI."""
    import subprocess
    try:
        result = subprocess.run(
            [os.environ.get('LSFG_VKD3D_COMPILER', 'vkd3d-compiler'), '-x', 'dxbc-tpf',
             '-b', 'spirv-binary', '-o', str(out_spv), str(blob_path)],
            capture_output=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    ok = result.returncode == 0 and out_spv.exists()
    if not ok and out_spv.exists():
        out_spv.unlink()   # never leave a partial or empty .spv behind
    return ok


def transpile_to_spirv(dxbc_dir, out_dir=None, force=False):
    """Transpile every .dxbc in dxbc_dir to SPIR-V with vkd3d-compiler.

    Returns the number of shaders newly transpiled. Without the tool, or when a shader fails,
    no .spv is written for it (no placeholder files).
    """
    out_dir = Path(out_dir) if out_dir else dxbc_dir.parent / 'spirv'
    spv_dir = out_dir / 'shaders'
    dxbc_files = sorted(dxbc_dir.glob('*.dxbc')) if dxbc_dir.is_dir() else []
    if not dxbc_files:
        return 0
    spv_dir.mkdir(parents=True, exist_ok=True)

    print(f'[lsfg] transpile: {len(dxbc_files)} DXBC file(s) to SPIR-V', file=sys.stderr)
    done = failed = 0
    for dxbc_file in dxbc_files:
        out_spv = spv_dir / f'{dxbc_file.stem}.spv'
        if out_spv.exists() and not force:
            continue
        if _try_vkd3d_blob(dxbc_file, out_spv):
            done += 1
        else:
            failed += 1
    if failed:
        print(f'[lsfg] {failed} shader(s) not transpiled (vkd3d-compiler missing or failed)', file=sys.stderr)
    return done


def _write_lsfgpack(out_dir, blobs, force=False):
    """Write the .lsfgpack manifest (metadata.json) into out_dir."""
    meta_path = Path(out_dir) / 'metadata.json'
    meta = {
        'format': 'lsfgpack',
        'version': 1,
        'blob_count': len(blobs),
        'blobs': [asdict(b) for b in blobs],
        'note': 'DXBC blobs only; transpile to SPIR-V with vkd3d-compiler (see transpile_to_spirv)',
        'spirv_ready': False,
    }
    if not meta_path.exists() or force:
        meta_path.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')


def main():
    """CLI: python -m porter.lsfg_extract <dll_path> [--out <dir>] [--force]"""
    import argparse
    p = argparse.ArgumentParser(
        prog='porter lsfg-extract',
        description='Extract LSFG shaders from Lossless.dll')
    p.add_argument('dll', help='path to the extracted Lossless.dll')
    p.add_argument('--out', default=None,
                    help='output directory (default: <dll>/lsfg/)')
    p.add_argument('--force', action='store_true',
                    help='overwrite existing outputs')
    args = p.parse_args()

    dll_path = Path(args.dll)
    if not dll_path.is_file():
        print(f'[lsfg] not a file: {dll_path}', file=sys.stderr)
        sys.exit(1)

    out = Path(args.out) if args.out else dll_path.with_suffix('') / 'lsfg'
    blobs = extract_dll(dll_path, out, force=args.force)
    print(f'[lsfg] done: {len(blobs)} blob(s) in {out}')


if __name__ == '__main__':
    main()
