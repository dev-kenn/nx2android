d = open('Lossless.dll','rb').read()
off = 0; pos = []
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    pos.append(i); off = i+1

print(f'Total entries: {len(pos)}')
print()
for p in pos[:4]:
    f1 = int.from_bytes(d[p+4:p+8], 'little')
    f2 = int.from_bytes(d[p+8:p+12], 'little')
    print(f'@{p:#08x}: byte0={f1} ({f1:#06x}) byte4={f2} ({f2:#06x}) rest={d[p+12:p+20].hex()}')

# Check entry 0 in detail: look at what the "RDEF" chunk looks like
# RDEF is at +0x34 from blob start (offset +0x30 has value 0x00001314 = 4884)
p = pos[0]
print()
print(f'Entry 0: full first 100 bytes:')
h=' '.join(f'{b:02x}' for b in d[p:p+100])
a=''.join(chr(b) if 32<=b<=126 else '.' for b in d[p:p+100])
print(h); print(a)

# The DXBC spec says: magic(4) + size_of_blob(4) + chunk_table(4 bytes count + N*12 byte entries)
# After the offset table: each entry = {name(4), pad1(2), data_offset_in_blob(4), data_size(2), pad2(2)}
# But the blob in this file might have a DIFFERENT layout than standard DXBC
