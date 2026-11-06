import struct, hashlib
d = open('Lossless.dll', 'rb').read()
pe_off = struct.unpack_from('<I', d, 0x3C)[0]
ns = struct.unpack_from('<H', d, pe_off + 6)[0]
print(f'PE at {pe_off:#x}, sections: {ns}')

# Section table
st = pe_off + 24
sections = []
for i in range(min(ns, 10)):
    so = st + i * 40
    if so + 40 > len(d): break
    nm = ''.join(chr(d[x]) if 32 <= d[x] <= 126 else '.' for x in range(so, min(so + 8, len(d))))
    vsz = struct.unpack_from('<I', d, so + 16)[0]
    roff = struct.unpack_from('<I', d, so + 20)[0]
    rsz = struct.unpack_from('<I', d, so + 24)[0]
    sections.append((nm, vsz, roff, rsz))
    if rsz > 0 and roff < len(d):
        end = min(roff + rsz, len(d))
        region = d[roff:end]
        dxbc_count = region.count(b'DXBC')
        sha1 = hashlib.sha256(region).hexdigest()[:12]
        print(f'[{i:2d}] {nm!r}: vsz=0x{vsz:X} roff=0x{roff:X} rsz=0x{rsz:X} DXBC={dxbc_count} sha={sha1}')
        if dxbc_count > 0:
            # Found DXBC in section data - do full validation!
            po = 0
            while True:
                p = region.find(b'DXBC', po)
                if p < 0: break
                abs_off = roff + p
                if abs_off + 16 <= len(d):
                    hdr = struct.unpack_from('<II', d, abs_off + 8)[0]
                    hsz = (hdr >> 0) & 0xFFFFFFFF
                    tsz = (hdr >> 32)
                    valid = 0x1C <= hsz < 0x2000 and tsz > hsz and (abs_off + tsz) <= len(d)
                    print(f'    DXBC@{abs_off:#x}: hdr=0x{hsz:X} total=0x{tsz:X} valid={valid}')
                    if valid:
                        blob = d[abs_off:abs_off+min(tsz, 4096)]
                        strings = {}
                        if hsz >= 0x14:
                            str_off = struct.unpack_from('<I', blob, hsz + 4)[0]
                            end_of_str_table = hsz + str_off + 8
                            so2 = hsz + str_off + 4
                            while so2 < end_of_str_table - 1 and (blob[so2] != 0 or (so2+1 < len(blob) and blob[so2+1] != 0)):
                                s = b''
                                while so2 + len(s) < min(end_of_str_table, len(blob)) and blob[so2 + len(s)] != 0:
                                    s += bytes([blob[so2 + len(s)]])
                                    if len(s) > 1024: break
                                if s: strings[s.decode('utf-8', errors='replace')] = ''
                                so2 += len(s) + 1
                            for k in list(strings.keys())[:5]:
                                print(f'    STRING: {k!r}')
                        # Check chunk table
                        chunks_off = abs_off + hsz
                        cc = struct.unpack_from('<I', d, chunks_off)[0]
                        print(f'    Chunks: {cc}')
                        for c in range(min(cc, 6)):
                            co = chunks_off + c * 12
                            nb = d[co:co+4]
                            csz = struct.unpack_from('<I', d, co+6)[0]
                            try:
                                cn = nb.decode('ascii')
                                if all(32 <= ord(x) <= 126 for x in cn):
                                    print(f'    Chunk #{c}: {cn!r} size={csz}')
                            except: pass
                po = p + 1

# Also check the file header at PE+10 (FileHeader struct)
print()
fh_off = pe_off + 4 + 20  # SizeOfOptionalHeader is at PE+28, but FileHeader starts at PE+24
print(f'FileHeader @ {pe_off + 24}:')
flags = struct.unpack_from('<H', d, pe_off + 26)[0]
num_opt = struct.unpack_from('<H', d, pe_off + 28)[0]
print(f'  Characteristics: 0x{flags:X}')
print(f'  SizeOfOptionalHeader: {num_opt}')

# Check actual bytes at the PE signature area more carefully
print()
sig_bytes = list(d[pe_off:pe_off+4])
print(f'PE sig bytes: {[f"0x{x:02X}" for x in sig_bytes]}')
print(f'Same as "PE\\x00\\x00": {sig_bytes == [0x50, 0x45, 0x00, 0x00]}')

