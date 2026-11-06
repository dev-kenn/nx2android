import struct

d = open('Lossless.dll','rb').read()

# Check PE headers directly
dos_magic = int.from_bytes(d[0:2], 'little')
pe_off = int.from_bytes(d[0x3C:0x40], 'little')
print(f'DOS Magic: {dos_magic:#06x} (expect 0x5A4D)')
print(f'PE offset: 0x{pe_off:X}')

if dos_magic == 0x5A4D and pe_off < len(d):
    pe_sig = int.from_bytes(d[pe_off:pe_off+4], 'little')
    print(f'PE Signature: {pe_sig:#010x} (expect 0x00004550)')
    
    # Parse PE header
    opt_start = pe_off + 4 + 20
    magic = int.from_bytes(d[opt_start:opt_start+2], 'little')
    print(f'PE Optional Magic: {magic:#06x} (expect 0x20B for PE32+)')
    
    # Resource table at offset 0xF8 from optional header start
    rsrc_off = int.from_bytes(d[opt_start+0xF8:opt_start+0xFC], 'little')
    rsrc_sz = int.from_bytes(d[opt_start+0xFC:opt_start+0x100], 'little')
    print(f'Resource RVA: 0x{rsrc_off:X} Size: 0x{rsrc_sz:X}')
    
    # Find which PE section contains the resource table
    sec_count = int.from_bytes(d[pe_off+6:pe_off+8], 'little')
    sec_start = pe_off + 24
    for i in range(sec_count):
        s_off = sec_start + i*40
        name = d[s_off:s_off+8]
        vaddr = int.from_bytes(d[s_off+12:s_off+16], 'little')
        vsize = int.from_bytes(d[s_off+8:s_off+12], 'little')
        foff = int.from_bytes(d[s_off+16:s_off+20], 'little')
        fsz = int.from_bytes(d[s_off+20:s_off+24], 'little')
        if rsrc_off >= vaddr and rsrc_off < vaddr + vsize:
            print(f'  -> Resource section found! RVA=0x{rsrc_off:X} FOFFSET={vaddr} FSIZE={fsz}')
            res_file_off = (rsrc_off - vaddr) + foff
            print(f'  -> Resource data starts at file offset: 0x{res_file_off:X}')

# Check first few DXBC entries for SPIR-V magic within them
print()
print('=== DXBC entries with byte preview ===')
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

for p in offsets[:10]:
    size = int.from_bytes(d[p+4:p+8], 'little')
    end = min(p + size, len(d))
    chunk = d[p:end]
    spv_idx = chunk.find(bytes([0x13, 0x02, 0x03, 0x0f]))
    rdef_idx = chunk.find(b'RDEF')
    print(f'@ {p:#08x} size={size:#08x}: DXBC; SPIR-V@={spv_idx if spv_idx>=0 else "N/A"} RDEF@={rdef_idx if rdef_idx>=0 else "N/A"}')
    # Print the first 32 bytes as hex + ascii
    print(f'  First 32: {" ".join(f"{b:02x}" for b in chunk[:32])}')
