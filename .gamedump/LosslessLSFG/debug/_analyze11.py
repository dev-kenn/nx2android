import struct
d = open('Lossless.dll','rb').read()

# Check the 202 DXBC entries more carefully
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

print(f'Total DXBC markers: {len(offsets)}')
print(f'File size: {len(d):#x}')

# All first bytes of "size" field in each entry (byte at offset 4 from marker)
first_bytes_of_size = [d[o+4] for o in offsets]
print(f'\nFirst byte of "size" field (byte at +4 from DXBC marker):')
print(f'  Unique values: {set(first_bytes_of_size)}')

# Check the actual data after each DXBC marker
print(f'\n=== First 6 entries: structure analysis ===')
for idx in range(min(6, len(offsets))):
    p = offsets[idx]
    size_byte = d[p+4]
    next_p = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    
    # The first 8 bytes after DXBC marker
    b0_7 = d[p:p+8]
    
    print(f'\nEntry {idx} @ 0x{p:X}:')
    print(f'  First 4 bytes: {" ".join(f"{b:02x}" for b in b0_7[:4])}')
    print(f'  Next 4 bytes:  {" ".join(f"{b:02x}" for b in b0_7[4:])}')
    
    # Check what follows the first 8 bytes (12 bytes of DXBC header would be chunk table)
    if p + 16 <= len(d):
        chunk_count = int.from_bytes(d[p+12:p+16], 'little')
        print(f'  Chunk count field: {chunk_count} (0x{chunk_count:x})')
    
    # What's at offset 52 from marker? (RDEF position)
    if p + 52 <= len(d):
        rdef_bytes = d[p+48:p+60]
        print(f'  At +48:   {" ".join(f"{b:02x}" for b in rdef_bytes[:4])} = {chr(rdef_bytes[0]) if 32<=rdef_bytes[0]<=126 else "?"}{chr(rdef_bytes[1]) if 32<=rdef_bytes[1]<=126 else ""}{chr(rdef_bytes[2]) if 32<=rdef_bytes[2]<=126 else ""}{chr(rdef_bytes[3]) if 32<=rdef_bytes[3]<=126 else ""}')
    
    # What is the data between DXBC marker and RDEF?
    rdef_pos = p + 48  # The RDEF string starts at offset 48 from marker
    
    print(f'  Blob size (to next entry): {next_p - p:#x} ({next_p-p})')
    
    # Print a hex dump of first 64 bytes
    end = min(p + 64, next_p)
    print(f'  First 64 bytes: {" ".join(f"{d[p+i]:02x}" for i in range(min(64, end-p)))}')

# Also check if the DXBC markers are part of a structured array
print(f'\n=== DXBC marker positions ===')
for idx in range(min(10, len(offsets))):
    print(f'  Entry {idx:3d}: file_offset=0x{offsets[idx]:X}')

# Check if these could be a PE resource section that was manually extracted/replicated
# Look for any recognizable PE-like structure starting from the first DXBC entry
print(f'\n=== Is there a PE header before the first DXBC? ===')
first = offsets[0]
print(f'First DXBC at 0x{first:X}')
# Scan backwards for MZ magic
for i in range(first-2, max(0, first-200), -1):
    if d[i:i+2] == b'MZ':
        print(f'Found MZ at offset 0x{i:X}!')
        break

print('\nDone!')