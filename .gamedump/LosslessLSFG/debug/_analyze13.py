d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

print(f"Total DXBC entries: {len(offsets)}")

for idx in range(min(15, len(offsets))):
    p = offsets[idx]
    blob_end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    actual_size = blob_end - p
    
    v_at_20 = int.from_bytes(d[p+20:p+24], 'little')
    match = 'YES' if v_at_20 == actual_size else 'NO'
    
    print(f"  Entry {idx:3d}: size={actual_size:#x}({actual_size}) @20={v_at_20:#x}({v_at_20}) match={match}")

print("\nSearching for which offset contains the blob size:")
for idx in range(5):
    p = offsets[idx]
    blob_end = offsets[idx+1] if idx < len(offsets)-1 else len(d)
    actual_size = blob_end - p
    
    print(f"  Entry {idx}: looking for value {actual_size:#x} in first 64 bytes...")
    for off2 in range(4, 64):
        val = int.from_bytes(d[p+off2:p+off2+4], 'little')
        if val == actual_size:
            print(f"    FOUND at +0x{off2:X}!")

# Full hex dump of first entry (Entry 0)
print("\n=== Entry 0: full hex dump (first 100 bytes) ===")
p = offsets[0]
blob_end = offsets[1] if len(offsets) > 1 else len(d)
for i in range(0, min(100, blob_end-p), 32):
    row = d[p+i:p+i+32]
    hex_str = ' '.join(f'{b:02x}' for b in row)
    print(f"  +{i:04X}: {hex_str}")

print("\nDone!")