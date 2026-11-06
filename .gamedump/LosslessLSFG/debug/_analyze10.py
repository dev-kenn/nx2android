import struct
d = open('Lossless.dll','rb').read()

print(f'File size: {len(d):#x} ({len(d)})')

# Check what's at file offset 0x534000 (the "Resource RVA" from PE headers)
target = 0x534000
if target < len(d):
    print(f'\n=== At file offset 0x{target:X} (the "Resource RVA") ===')
    chunk = d[target:target+64]
    print('Hex:', ' '.join(f'{b:02x}' for b in chunk))
    
    # Look for any recognizable markers
    if b'DXBC' in chunk:
        print('Contains DXBC!')
    if b'RDEF' in chunk:
        print('Contains RDEF!')
    
    # Try to find where DXBC entries begin near here
    off = target
    while True:
        i = d.find(b'DXBC', off)
        if i < 0 or i > target + 0x1000: break
        print(f'  Found DXBC at file offset: 0x{i:X}')
        if i >= target + 0x200: break
        off = i + 1

# Also check the first PE optional header fields for clues
pe_off = 0x130
opt_start = pe_off + 24

print(f'\n=== PE Optional Header (first 80 bytes) ===')
for i in range(0, min(80, len(d)-opt_start), 4):
    val = int.from_bytes(d[opt_start+i:opt_start+i+4], 'little')
    print(f'  +{i:#06x}: {val:#012x}')

# Check what the first few PE optional header entries look like  
print(f'\n=== Key PE Optional Header fields ===')
magic   = int.from_bytes(d[opt_start:opt_start+2], 'little')
linker  = d[opt_start+2]
entrypt = int.from_bytes(d[opt_start+8:opt_start+12], 'little')
sizecode= int.from_bytes(d[opt_start+12:opt_start+16], 'little')
print(f'Magic={magic:#06x} LinkerVer={linker:#04x} EntryPoint={entrypt:#010x} SizeOfCode={sizecode:#010x}')

# Data directories start at +0x98 from opt hdr start (for PE32+)
print(f'\n=== Data Directories (first 6 entries) ===')
dd_base = opt_start + 0xA8  # After PE signature + file header, data dirs at 0xA8 for PE32+
# Actually standard: for PE32+ the data directory starts after the optional header fields
# The offset of data directories depends on the PE format version
# For PE32+: Data dir entry = (StandardFields - 0x90) + (DllCharacteristics-...) 
# Let me just try common offsets

# Try standard PE32+ location: section header follows optional header at +0xE0, but data dirs are embedded
# Actually for pe_offset: dd[0] RVA is at offset 0xA8 from opt hdr start (for x64)
for i in range(6):
    off = opt_start + 0xA8 + i*8
    if off + 8 > len(d): break
    rv = int.from_bytes(d[off:off+4], 'little')
    sz = int.from_bytes(d[off+4:off+8], 'little')
    names = ['EXPORT', 'IMPORT', 'RESOURCE', 'EXCEPTION', 'SECURITY', 'RELOC']
    print(f'  [{i}] {names[i]}: RVA={rv:#010x} Size={sz:#010x}')

print('\nDone!')