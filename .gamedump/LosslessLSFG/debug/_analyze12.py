import struct
d = open('Lossless.dll','rb').read()

offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

# Let me analyze the pattern across all entries more carefully
print("=== Entry structure analysis (first entry in detail) ===")
p = offsets[0]
blob_end = offsets[1] if len(offsets) > 1 else len(d)

print(f"Entry 0: start=0x{p:X} end=0x{blob_end:X} size={blob_end-p:#x}({blob_end-p})")
print()

# The structure appears to be:
# DXBC(4) + field_A(4) + some_payload(?) + chunk_table_header(16?) + RDEF_entry(...)
# Let me find the pattern by looking at byte 0x14 (20 from marker) which is "01 00 00 00" 
# and byte 0x18-1B which are varying offsets

# For Entry 0:
print(f"Entry 0 hex dump (first 100 bytes):")
for row in range(6):
    row_start = p + row*16
    row_data = d[row_start:row_start+16]
    hex_str = ' '.join(f'{b:02x}' for b in row_data)
    print(f"  +{row*0x10:X}: {hex_str}")

# Let me look at Entry 1 which is different
print(f"\n\nEntry 1 hex dump (first 100 bytes):")
p1 = offsets[1]
blob_end1 = offsets[2] if len(offsets) > 2 else len(d)
for row in range(6):
    row_start = p1 + row*16
    row_data = d[row_start:row_start+16]
    hex_str = ' '.join(f'{b:02x}' for b in row_data)
    print(f"  +{row*0x10:X}: {hex_str}")

# What if the first 4 bytes after "DXBC" (byte at +4) is NOT part of DXBC?
# What if "DXBC" is a delimiter and what follows is actually the actual content?
print("\n\n=== Hypothesis: DXBC is just a marker/delimiter ===")
print("First 20 bytes after each DXBC marker:")
for idx in range(min(5, len(offsets))):
    p = offsets[idx]
    size_byte = d[p+4]
    after = d[p+5:p+25]
    print(f"  Entry {idx}: size_byte={size_byte:#x}({size_byte}) next_bytes={' '.join(f'{b:02x}' for b in after)}")

# The key question: is this a .NET/managed assembly?
# .NET assemblies use "DXBC" as the PE magic (it's called "ManagedPEHeader" or similar)
# Actually no, but .NET uses "MZ" + CLR header with specific format

print("\n\n=== Is this a .NET/CLR managed binary? ===")
if d[0:2] == b'MZ':
    pe_off = int.from_bytes(d[0x3C:0x40], 'little')
    if pe_off + 8 < len(d):
        # Look for PE+ magic and .NET directory entry
        magic = int.from_bytes(d[opt_start:opt_start+2], 'little')
        print(f"PE magic: {magic:#06x}")
        
        # Check if there's a CLI/CLR header signature
        num_sects = int.from_bytes(d[pe_off+6:pe_off+8], 'little')
        opt_hdr_size = int.from_bytes(d[pe_off+16:pe_off+18], 'little')
        print(f"NumSections={num_sects} OptHdrSize={opt_hdr_size}")
        
        # Check the .NET directory entry (usually at index 14 of data directories)
        # For PE32+, data dirs start at +0x98 from opt hdr
        
        # Actually, let me check if this is a .NET assembly by looking for 
        # the "COR2 header" signature which would indicate CLI/managed code
        # COR2 = 0x534A4200 (little-endian: 00 40 4A 53)
        
        dot = pe_off + 24 + opt_hdr_size
        print(f"\nOpt hdr ends at: {dot:#x}")
        
        # Check for CLR/CLI header in the .NET data directory
        # For PE32+, entry 14 (.NET) RVA is at offset +0xC8 from opt hdr start (0x98 + 0x30)
        dot_rva_off = pe_off + 24 + 0x98 + 8*14  # entry 14: 14 * 8 bytes each
        if dot_rva_off + 8 <= len(d):
            dot_rva = int.from_bytes(d[dot_rva_off:dot_rva_off+4], 'little')
            dot_sz  = int.from_bytes(d[dot_rva_off+4:dot_rva_off+8], 'little')
            print(f".NET Dir Entry: RVA={dot_rva:#010x} Size={dot_sz:#010x}")

# Let me look at the very beginning of the file
print("\n\n=== File header (first 64 bytes) ===")
for i in range(0, min(64, len(d)), 16):
    row = d[i:i+16]
    print(f"  +{i:04X}: {' '.join(f'{b:02x}' for b in row)}")

print("\nDone!")