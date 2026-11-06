d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

print(f"Total entries: {len(offsets)}")

# Let me check what the first entry's content looks like after all known fields
for idx in range(min(3, len(offsets))):
    p = offsets[idx]
    blob_end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    blob_size = blob_end - p
    
    print(f"\nEntry {idx} @ 0x{p:X} size={blob_size:#x}")
    
    # Print all bytes in the entry (it's small enough for some)
    for i in range(0, min(256, blob_size), 16):
        row = d[p+i:p+i+16]
        hex_str = ' '.join(f'{b:02x}' for b in row)
        print(f"  +{i:04X}: {hex_str}")

print("\nDone!")