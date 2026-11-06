d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

# Each entry's payload consists of: 
# [uint32_header(20)] + [chunk_table_entries] + [shader_data_payload]
# The last chunk_entry points to the shader data with the LARGEST offset

# Find the largest-offset chunk for each entry, and print its contents
print("Finding shader bytecode region in each entry:")

for idx in range(min(10, len(offsets))):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    
    # Parse chunk table starting at +0x18 (after uint32 count field)
    nchunks = int.from_bytes(d[p+24:p+25], 'little')  # Single byte!
    max_offset = 0
    max_chunk_idx = -1
    
    print(f'\nEntry {idx} (size={end-p:#x}, chunks={nchunks}):')
    
    for j in range(nchunks):
        eoff = p + 25 + j * 8  # Each entry: uint32_name(4) + uint32_offset(4)
        chunk_name_byte = d[eoff]
        chunk_off = int.from_bytes(d[eoff+1:eoff+5], 'little')
        print(f'  Chunk {j} (byte={chunk_name_byte}): offset_in_blob=0x{chunk_off:X}')
        
        if chunk_off > max_offset:
            max_offset = chunk_off
            max_chunk_idx = j
    
    # The shader bytecode should be at p + max_offset
    data_start = p + max_offset
    data_end = end
    print(f'  Shader starts at file offset {data_start:#x} (entry start + 0x{max_offset:X})')
    
    if data_start < len(d) and data_start + 32 <= min(end, len(d)):
        print('  First 32 bytes of shader data: ', end='')
        for b in d[data_start:data_start+32]:
            print(f'{b:02x}', end=' ')
        print()

print("\nDone!")