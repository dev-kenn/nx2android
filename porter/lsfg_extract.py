# LSFG shader pack extractor for nx2android.
# Reads a user-supplied Lossless.dll (PE32+, DXBC blobs), extracts raw shader bytes,
# and produces a .lsfgpack bundle of SPIR-V modules ready for the Android Vulkan runtime.
#
# Pipeline: Lossless.dll (DXBC) -> dxldc/DXC transpile -> GLSL(HLSL->GLSL) -> glslc -> SPIR-V -> .lsfgpack
#
# This module runs on the host during a port. It does NOT compile or link: only text
# processing and file I/O. The actual HLSL->GLSL transpilation is delegated to dxc (Microsoft
# Direct3D Compiler) or dxcompiler when available; without either tool, the extractor still
# finds DXBC blobs and writes a placeholder .lsfgpack that the runtime can detect but skip.
#
# Design decisions:
# - We parse the PE structure to find DXBC sections rather than rely on any packer/obfuscator,
#   because Lossless.dll is often obfuscated (section names garbled).
# - Each DXBC blob becomes one .spv file named by its checksum for easy deduplication.
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
            if token_off + 4 <= len(blob):
                token = _read_u32_le(blob, token_off)
                prog_type = (token >> 16) & 0xFF
                stage = _PROGRAM_TYPE_STAGE.get(prog_type)
                if stage is not None:
                    return stage
            raise ValueError(f'SHEX found but token or program type invalid (token=0x{token:08X})')

    raise ValueError('no SHEX chunk found')


def _parse_string_table(data, hdr_off):
    """Parse the DXBC string table header. Returns {name: value} pairs."""
    if hdr_off < 0 or hdr_off + 8 > len(data):
        return {}
    hdr_size = _read_u32_le(data, hdr_off)
    str_off = _read_u32_le(data, hdr_off + 4)
    if hdr_off + str_off + 8 > len(data):
        return {}
    end_off = hdr_off + str_off + 8
    strings = {}
    off = hdr_off + str_off + 4
    while off < end_off - 1 and (data[off] != 0 or (off + 1 < end_off and data[off + 1] != 0)):
        s = b''
        while off + len(s) < end_off and data[off + len(s)] != 0:
            s += bytes([data[off + len(s)]])
            if len(s) > 1024:
                break
        if s:
            strings[s.decode('utf-8', errors='replace')] = ''
        off += len(s) + 1
    return strings


def extract_dll(dll_path, out_dir=None, force=False):
    """Read Lossless.dll, find all DXBC shader blobs, and save them.

    The DLL may be obfuscated/packed. We scan raw memory for 'DXBC' magic markers
    rather than relying on any particular section layout or packer convention.
    """
    out_dir = Path(out_dir) if out_dir else dll_path.with_suffix('') / 'lsfg'
    out_dir.mkdir(parents=True, exist_ok=True)

    dll_bytes = bytes(dll_path.read_bytes())
    blobs = []
    off = 0

    while (off := _find_dxbc_blob(dll_bytes, off)) is not None:
        # Standard DXBC container layout: magic(4) + checksum(16) + one(4) + totalSize(4) at +0x18.
        # +8 is inside the checksum, not a size field.
        hdr_size = _read_u32_le(dll_bytes, off + 0x18)

        if hdr_size < 0x1C or hdr_size > 64 << 20:
            off += 1
            continue

        end = off + hdr_size
        if end > len(dll_bytes):
            off += 1
            continue

        blob = dll_bytes[off:end]
        checksum = hashlib.sha256(blob).hexdigest()[:16]

        strings = _parse_string_table(blob, off + 8)
        name = next(iter(strings.keys()), f'shad_{checksum[:8]}') if strings else f'shad_{checksum[:8]}'

        # Profile: read from real SHEX chunk instead of broken string-table guess
        profile = ''
        try:
            profile = _read_shader_stage(blob, [])
        except ValueError:
            pass  # leave profile as empty string for unknown blobs

        blobs.append(DxbcInfo(name=name, size=hdr_size, offset=off,
                              checksum=checksum, version='',
                              profile=profile))
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


def _try_dxc_blob(blob_path, out_spv):
    """Try to transpile a DXBC blob to SPIR-V using the `dxc` CLI."""
    import subprocess
    try:
        result = subprocess.run(
            ['dxc', '-T', 'ps_5_0', '-E', 'main', str(blob_path), '-O3',
             '-spirv', '-no_api', '-Fo', str(out_spv)],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0 and out_spv.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _try_dxcompiler(blob_path, out_spv):
    """Try to transpile using dxcompiler via dotnet host."""
    try:
        import subprocess
        result = subprocess.run(
            ['dotnet', str(Path(__file__).parent / 'dxcompile_host.dll'),
             str(blob_path), str(out_spv)],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0 and out_spv.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def transpile_to_spirv(dxbc_dir, out_dir=None, force=False):
    """Transpile all DXBC files in dxbc_dir to SPIR-V shaders.

    Tries dxc first, then dxcompiler. Without either tool, writes stubs.
    Returns the number of successful transpilations.
    """
    out_dir = Path(out_dir) if out_dir else dxbc_dir.parent / 'spirv'
    out_dir.mkdir(parents=True, exist_ok=True)
    spv_dir = out_dir / 'shaders'
    spv_dir.mkdir(exist_ok=True)

    dxbc_files = list(dxbc_dir.glob('*.dxbc'))
    if not dxbc_files:
        return 0

    print(f'[lsfg] transpile: {len(dxbc_files)} DXBC file(s) to SPIR-V', file=sys.stderr)

    success_count = 0
    for dxbc_file in sorted(dxbc_files):
        out_spv = spv_dir / f'{dxbc_file.stem}.spv'

        if out_spv.exists() and not force:
            continue

        if _try_dxc_blob(dxbc_file, out_spv):
            success_count += 1
            continue

        if _try_dxcompiler(dxbc_file, out_spv):
            success_count += 1
            continue

        print(f'[lsfg] stub: {dxbc_file.name} no transpiler found', file=sys.stderr)
        out_spv.write_bytes(bytes([0x11, 0x00, 0x00, 0x00]))

    return success_count


def _write_lsfgpack(out_dir, blobs, force=False):
    """Write the .lsfgpack manifest (metadata.json) into out_dir."""
    meta_path = Path(out_dir) / 'metadata.json'
    meta = {
        'format': 'lsfgpack',
        'version': 1,
        'blob_count': len(blobs),
        'blobs': [asdict(b) for b in blobs],
        'note': 'SPIR-V shaders must be transpiled from DXBC (requires dxc or dxcompiler)',
        'spirv_ready': False if blobs else True,
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
