# Tests for porter/lsfg_extract.py
import json
import struct
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from porter import lsfg_extract


def make_dxbc(total_size, program_type=5):
    """Minimal valid DXBC container: header + one SHEX chunk, padded to total_size."""
    token = (program_type << 16) | 0x50  # program type, version 5.0
    chunk = b"SHEX" + struct.pack("<II", 4, token)
    chunk_off = 0x24
    hdr = (b"DXBC" + b"\x00" * 16 + struct.pack("<III", 1, total_size, 1)
           + struct.pack("<I", chunk_off))
    blob = hdr + chunk
    assert total_size >= len(blob)
    return blob + b"\x00" * (total_size - len(blob))


class TestShaderStage(unittest.TestCase):
    def test_stage_decoding(self):
        for ptype, name in [(0, "ps"), (1, "vs"), (5, "cs")]:
            self.assertEqual(lsfg_extract._read_shader_stage(make_dxbc(128, ptype), []), name)

    def test_no_shex_raises(self):
        with self.assertRaises(ValueError):
            lsfg_extract._read_shader_stage(b"DXBC" + b"\x00" * 60, [])

    def test_extract_records_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            dll.write_bytes(b"\x00" * 16 + make_dxbc(96, 5))
            blobs = lsfg_extract.extract_dll(dll, Path(tmp) / "out")
            self.assertEqual([b.profile for b in blobs], ["cs"])

    def test_truncated_magic_at_eof(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            dll.write_bytes(b"junk DXBC")
            self.assertEqual(lsfg_extract.extract_dll(dll, Path(tmp) / "out"), [])


class TestDxbcInfo(unittest.TestCase):
    def test_default_profile(self):
        blob = lsfg_extract.DxbcInfo(name="test", size=1024, offset=0, checksum="abc123", version="ps_5_0")
        self.assertEqual(blob.profile, "")


class TestHelpers(unittest.TestCase):
    def test_read_u32_le(self):
        data = struct.pack("<I", 66)
        self.assertEqual(lsfg_extract._read_u32_le(data, 0), 66)

    def test_find_dxbc_blob_found(self):
        data = b"hello DXBC world"
        idx = lsfg_extract._find_dxbc_blob(data)
        self.assertEqual(idx, 6)

    def test_find_dxbc_blob_not_found(self):
        data = b"no magic here"
        idx = lsfg_extract._find_dxbc_blob(data)
        self.assertIsNone(idx)


class TestExtractDll(unittest.TestCase):
    def _make_stub(self, size=512, program_type=5):
        return make_dxbc(size, program_type)

    def test_no_blobs_in_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            dll.write_bytes(b"no DXBC here at all")
            out = Path(tmp) / "out"
            blobs = lsfg_extract.extract_dll(dll, out)
            self.assertEqual(len(blobs), 0)

    def test_one_blob_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            blob = self._make_stub(256)
            content = b"\x00" * 100 + blob + b"\x00" * 100
            dll.write_bytes(content)
            out = Path(tmp) / "out"
            blobs = lsfg_extract.extract_dll(dll, out)
            self.assertEqual(len(blobs), 1)
            self.assertEqual(blobs[0].size, 256)

    def test_multiple_blobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            a = self._make_stub(128)
            b_ = self._make_stub(64)
            dll.write_bytes(a + b"\x00" * 20 + b_)
            out = Path(tmp) / "out"
            blobs = lsfg_extract.extract_dll(dll, out)
            self.assertEqual(len(blobs), 2)

    def test_metadata_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            dll.write_bytes(self._make_stub(64))
            out = Path(tmp) / "out"
            lsfg_extract.extract_dll(dll, out)
            meta = json.loads((out / "metadata.json").read_text())
            self.assertEqual(meta["format"], "lsfgpack")
            self.assertEqual(meta["version"], 1)

    def test_metadata_blob_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "Lossless.dll"
            blob = self._make_stub(64)
            dll.write_bytes(blob + b"\x00\x00" + blob)
            out = Path(tmp) / "out"
            blobs = lsfg_extract.extract_dll(dll, out)
            meta = json.loads((out / "metadata.json").read_text())
            self.assertEqual(meta["blob_count"], len(blobs))


class TestTranspile(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            dxbc = Path(tmp) / "dxbc"
            spv = Path(tmp) / "spv"
            n = lsfg_extract.transpile_to_spirv(dxbc, spv)
            self.assertEqual(n, 0)

    def test_no_dxc_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            dxbc = Path(tmp) / "dxbc"
            spv = Path(tmp) / "spv"
            dxbc.mkdir()
            (dxbc / "abc123.dxbc").write_bytes(b"some DXBC bytes")
            with unittest.mock.patch('subprocess.run', side_effect=FileNotFoundError):
                n = lsfg_extract.transpile_to_spirv(dxbc, spv)
            self.assertEqual(n, 0)
            self.assertEqual(list((spv / 'shaders').glob('*.spv')), [])   # no placeholder files


if __name__ == "__main__":
    unittest.main()
