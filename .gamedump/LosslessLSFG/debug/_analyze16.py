d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

# The key insight: the first entry has a variable-length header of ~24 bytes
# followed by what appears to be chunk data
# Let me check: does each entry have a HEADER_SIZE field somewhere?

# For Entry 0: look at the blob from DXBC marker to end
p = offsets[0]
end = offsets[1]
print(f'Entry 0: file_offset=0x{p:X}, size={end-p:#x}')

# Look for any pattern in the first bytes after "DXBC"
# Byte 4-7: variable
# Byte 8-15: variable  
# Byte 16-19: uint32 (seems to be count or hash)
# Byte 20-23: uint32 = blob_size

# Check what happens if we interpret Entry 0's structure differently
# Maybe the first entry has a DIFFERENT header size!

# Let me try: Header is bytes 0-19 (20 bytes), then content starts at +0x14
print(f'\nFirst 64 bytes after DXBC marker:')
for i in range(0, min(64, end-p), 16):
    chunk = d[p+i:p+i+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    print(f'  +{i:#06X}: {hex_str}')

# Now let me try a completely different approach: 
# What if "DXBC" entries are NOT containers but just markers pointing to 
# shader data that lives AFTER the entry's total size?

# Check Entry 1: DXBC at file offset 0x52F18, next DXBC at 0x571F0
# Maybe the actual shader is at a specific position WITHIN each entry?

print(f'\n\nLet me check: where does Entry 0\'s content end and Entry 1 begin?')
print(f'Entry 0 ends at file offset {end:#X}')
print(f'Entry 1 starts at file offset {offsets[1]:#X}')

# The space between end of Entry 0 header and start of Entry 1:
# Entry 0 total size = 5980 (0x1764)
# So entry content is from 0x51B68 to 0x532CC (exclusive)

# Actually, the first "DXBC" at offset 0x51B68 marks Entry 0's start
# The next "DXBC" at 0x52F18 marks Entry 1's start
# So Entry 0 = from 0x51B68 to 0x52F17 (total size 0x13B0)

# Now, the question is: does Entry 0 contain a "DXBC" text string INSIDE it?
# If yes, then there's a nested container!

print(f'\nSearching for second "DXBC" inside Entry 0:')
content = d[offsets[0]+4:end-offsets[0]-4+4]
pos = content.find(b'DXBC')
if pos >= 0:
    print(f'  Found DXBC at content offset +{pos:#x} (file offset {offsets[0]+4+pos:#x})')
    # Check what follows this inner DXBC
    inner_end = min(pos + 16, len(content))
    for i in range(min(16, inner_end - pos)):
        print(f'    +{pos+i:04X}: {content[pos+i]:02x}')
else:
    print(f'  No second DXBC found inside Entry 0')

print('\nDone!')