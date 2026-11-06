import struct
d = open('Lossless.dll','rb').read()
print(f'Size:{len(d)} DXBC:{d.count(b"DXBC")}')
spv_magic = bytes([0x13,0x02,0x03,0x0f])
sv = d.find(spv_magic)
print(f'SPIR-V magic: present={sv is not None} offset={sv:#x}' if sv >= 0 else 'SPIR-V magic: NOT FOUND')

# Section table with roff>0 rsz>0
pe_off = int.from_bytes(d[0x3C:0x40], 'little')
st = pe_off + 24
for i in range(6):
    so = st+i*40
    if so+40 > len(d): break
    rsz=int.from_bytes(d[so+24:so+28],'little')
    roff=int.from_bytes(d[so+20:so+24],'little')
    if rsz>0 and roff<len(d):
        end=min(roff+rsz,len(d))
        nm=''.join(chr(d[x]) if 32<=d[x]<=126 else '.' for x in range(so,min(so+8,so+40)))
        print(f'Sec[{i}] {nm!r}: roff=0x{roff:X} rsz=0x{rsz:X} file_bytes={end-roff}')

# Section 5 data preview (has real size starting at 0x60)
print()
print('Sec5@0x60 first 80 bytes:')
s=d[0x60:0xC0]
h=' '.join(f'{b:02x}' for b in s)
a=''.join(chr(b) if 32<=b<=126 else '.' for b in s)
print(h); print(a)

# Section 3 data preview (roff=0x210C, rsz=0x210C)  
print()
print('Sec3@0x210C first 80 bytes:')
s=d[0x210C:0x2150]
h=' '.join(f'{b:02x}' for b in s)
a=''.join(chr(b) if 32<=b<=126 else '.' for b in s)
print(h); print(a)

# Check if file starts with MZ
print()

