# Analyze Lossless.dll structure
d = open('Lossless.dll','rb').read()

offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

print(f"Total entries: {len(offsets)}")

for idx in range(min(5, len(offsets))):
    p = offsets[idx]
    blob_end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    
    b0 = int.from_bytes(d[p+4:p+8], 'little')
    b1 = int.from_bytes(d[p+8:p+12], 'little')
    chunk_tbl_size = int.from_bytes(d[p+12:p+16], 'little')
    
    print(f"\nEntry {idx} @ 0x{p:X}:")
    print(f"  First 16 bytes: {' '.join(f'{d[p+i]:02x}' for i in range(16))}")
    print(f"  As uint32 LE: size={b0:#x}, b48={b1:#x}, tbl_size={chunk_tbl_size:#x}")

# PE Section analysis
print("\n\n=== PE Section Headers ===")
pe_off = int.from_bytes(d[0x3C:0x40], 'little')
sec_count = int.from_bytes(d[pe_off+6:pe_off+8], 'little')
opt_size = int.from_bytes(d[pe_off+16:pe_off+18], 'little')

print(f"PE sig: {d[pe_off:pe_off+4]}")
print(f"Opt hdr size: {opt_size}")

for i in range(sec_count):
    s_off = pe_off + 24 + i*40
    name = d[s_off:s_off+8].rstrip(b'\x00')
    try:
        name_str = name.decode('ascii', errors='replace').strip()
    except:
        name_str = "?"
    print(f"Sec[{i}] {name_str}: VSize={int.from_bytes(d[s_off+8:s_off+12], 'little'):#x} "
          f"VAddr={int.from_bytes(d[s_off+12:s_off+16], 'little'):#x} "
          f"ROff={int.from_bytes(d[s_off+16:s_off+20], 'little'):#x} "
          f"RSz={int.from_bytes(d[s_off+20:s_off+24], 'little'):#x}")

# Check for resource section (.rsrc) specifically  
print("\n\n=== Looking for .rsrc or similar sections ===")
for i in range(sec_count):
    s_off = pe_off + 24 + i*40
    name = d[s_off:s_off+8]
    try:
        ns = name.decode('ascii', errors='replace').lower()
        if 'rsrc' in ns or 'data' in ns or 'code' in ns or '.r' in ns:
            print(f"Sec[{i}] {ns}: VA={int.from_bytes(d[s_off+12:s_off+16], 'little'):#x} ROFF=0x{int.from_bytes(d[s_off+16:s_off+20], 'little'):X}")
    except:
        pass

# Now: the first few PE sections have VA=0, which is weird. Let me check if they're at a different offset.
print("\n\n=== Check if DXBC entries are in a specific PE section ===")
rsrc_rva = int.from_bytes(d[pe_off+24+opt_size-8:pe_off+24+opt_size-4], 'little')
print(f"Resource RVA from opt hdr -0x8 to -0x4: 0x{rsrc_rva:X}")

# Actually for PE32+, the resource table RVA is at standard offset from start of optional header
# For PE32+ (magic=0x20B):
#   Data directories start at +112 from optional header start
#   Resource entry is at +112 to +120
opt_hdr_start = pe_off + 24 + opt_size
print(f"Opt hdr start: 0x{opt_hdr_start:X}")
