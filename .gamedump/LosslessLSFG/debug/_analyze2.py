import struct, hashlib
d = open('Lossless.dll', 'rb').read()

off = 0
found = 0
while found < 8:
    i = d.find(b'DXBC', off)
    if i < 0: break
    h = ' '.join(f'{b:02x}' for b in d[i:i+32])
    a = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in d[i:i+32])
    print(f'@{i:#08x}: {h}')
    print(f'        {a}')
    off = i + 1
    found += 1

print()
off = 0
pos = []
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    pos.append(i); off = i + 1

if len(pos) > 1:
    diffs = [pos[j+1]-pos[j] for j in range(min(len(pos)-1,40))]
    print(f'First 20 DXBC diffs: {diffs[:20]}')
    u = set(diffs[:30])
    print(f'Unique diffs: {sorted(u)}')

pe_off = struct.unpack_from('<I', d, 0x3C)[0]
st = pe_off + 24
ns = struct.unpack_from('<H', d, pe_off+6)[0]
print()
for i in range(min(ns, 10)):
    so = st + i*40
    if so+40 > len(d): break
    nm = ''.join(chr(d[x]) if 32<=d[x]<=126 else '.' for x in range(so, min(so+8, len(d))))
    roff = struct.unpack_from('<I', d, so+20)[0]
    rsz = struct.unpack_from('<I', d, so+24)[0]
    if rsz > 0:
        print(f'[{i}] {nm!r}: roff=0x{roff:X} rsz=0x{rsz:X}')

# Try DXBC header interpretation for every occurrence
print()
off2 = 0
while True:
    i = d.find(b'DXBC', off2)
    if i < 0: break
    if i+16 <= len(d):
        v4 = struct.unpack_from('<I', d, i+4)[0]
        t4 = struct.unpack_from('<I', d, i+8)[0]
        if v4 >= 0x1C and v4 < 0x2000 and t4 > v4 and (i+t4) <= len(d):
            print(f'VALID DXBC@{i:#x}: hdr=0x{v4:X} tot=0x{t4:X}')
    off2 = i+1
