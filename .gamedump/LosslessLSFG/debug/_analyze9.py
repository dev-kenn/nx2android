import struct
d = open('Lossless.dll','rb').read()
pe_off = 0x130
opt_start = pe_off + 24
opt_magic = int.from_bytes(d[opt_start:opt_start+2], 'little')
opt_size = int.from_bytes(d[opt_start+16:opt_start+18], 'little')
print(f'Opt hdr magic: {opt_magic:#06x} (expect 0x20B)')
print(f'Opt hdr size: {opt_size:#04x}')

if opt_magic == 0x20B:
    dd_start = opt_start + 0x98
    rva = int.from_bytes(d[dd_start:dd_start+4], 'little')
    sz = int.from_bytes(d[dd_start+4:dd_start+8], 'little')
    print(f'Data dir starts at: {dd_start:#x}')
    print(f'Resource RVA: {rva:#010x} Size: {sz:#010x}')
else:
    print('Not PE32+!')

dd_off = opt_start + 0xA8
print(f'Entry 14 (.NET?): RVA={int.from_bytes(d[dd_off:dd_off+4],"little"):#010x} Size={int.from_bytes(d[dd_off+4:dd_off+8],"little"):#010x}')

# Check section headers from actual PE structure
for i in range(6):
    s_off = pe_off + 24 + opt_size + i*40
    name = d[s_off:s_off+8].rstrip(b'\x00')
    vsz = int.from_bytes(d[s_off+8:s_off+12], 'little')
    va  = int.from_bytes(d[s_off+12:s_off+16], 'little')
    roff= int.from_bytes(d[s_off+16:s_off+20], 'little')
    rsz = int.from_bytes(d[s_off+20:s_off+24], 'little')
    try: ns = name.decode('ascii').strip()
    except: ns = '?'
    print(f'Sec[{i}] {ns}: VA={va:#x} RSZ={rsz} ROFF={roff:#x}')

print('Done!')