d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

# Entry 0 size = 0x13B0 = 5040 bytes
# That's big enough to contain shader code!
p = offsets[0]
end = offsets[1]
print(f'Entry 0: file_offset=0x{p:X} to 0x{end:X}, size={end-p:#x} ({end-p})')

# The header is ~24 bytes (from earlier analysis)
# So payload = d[p+24:end]
payload_start = p + 24
print(f'\nFirst 64 bytes of payload (at file offset 0x{payload_start:X}):')
for i in range(0, min(64, end - payload_start), 16):
    chunk = d[payload_start+i:payload_start+i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    print(f'  +{i:#4X}: {hex_str}')

# Check Entry 1 too (size=0x42D8, similar or larger)
p1 = offsets[1]
end1 = offsets[2] if len(offsets) > 2 else len(d)
print(f'\nEntry 1: file_offset=0x{p1:X} to 0x{end1:X}, size={end1-p1:#x}')

payload_start1 = p1 + 24
print('First 64 bytes of Entry 1 payload:')
for i in range(0, min(64, end1 - payload_start1), 16):
    chunk = d[payload_start1+i:payload_start1+i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    print(f'  +{i:#4X}: {hex_str}')

# Most important check: does Entry 0 start with a known shader magic?
print('\n\nChecking if first bytes could be valid shader signatures:')
for idx in range(min(3, len(offsets))):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    entry = d[p:end]
    
    # Check Entry 0 first bytes: 44 58 42 43 = "DXBC"
    # Check Entry 1 first bytes: same (44 58 42 43)
    
    # SPIR-V magic in the file is: 13 02 03 0f
    # This entry starts with: 44 58 42 43 = "DXBC"
    
    print(f'Entry {idx}: first 8 bytes = {entry[:8].hex()}')
    if idx == 0:
        # Entry 0 is special: header size at +0x14 = 5980 (0x1764) 
        # That means the actual content starts at some offset after the header
        # Let's check: is there a "DXBC" or similar magic inside?
        
        # Search for any recognizable pattern starting from byte +0x20 onwards
        print('  Checking bytes +0x20 to +0x40:')
        for i in range(0x20, min(0x40, len(entry))):
            print(f'    +{i:02X}: {entry[i]:02x}', end=' ')
            if (i - 0x20) % 8 == 7:
                print()

# Now try the big test: extract ALL 202 entries and check for SPIR-V
print('\n\nChecking all 202 entries for any shader signature:')
spv_count = 0
dxbc_count = 0
unknown_count = 0

for idx in range(len(offsets)):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    entry = d[p:end]
    
    # Check the first few bytes after header
    payload = entry[24:]  # Skip first 24 bytes of header
    
    if len(payload) >= 4:
        sig = payload[:4]
        
        # SPIR-V magic (little-endian uint32)
        if int.from_bytes(sig, 'little') == 0x07230201:
            spv_count += 1
        
        # DXBC/DXIL magic
        elif sig in [b'DXBC', b'DXIL']:
            dxbc_count += 1
        
        else:
            unknown_count += 1

print(f'SPIR-V: {spv_count}, DXBC/DXIL: {dxbc_count}, Unknown/Custom: {unknown_count}')

# For the entries with "Unknown" format, check their first byte patterns
print('\nSample of first 8 bytes of each entry\'s payload:')
for idx in range(min(20, len(offsets))):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    entry = d[p:end]
    payload = entry[24:]  # Skip first 24 bytes
    
    if len(payload) >= 8:
        sig = ' '.join(f'{b:02x}' for b in payload[:8])
        print(f'Entry {idx:3d}: {sig}')

print('\nDone!')