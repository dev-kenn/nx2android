d = open('Lossless.dll','rb').read()
off = 0
positions = []
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    positions.append(i)
    off = i + 1

print(f'Total DXBC markers: {len(positions)}')

# Entry 1 detailed analysis — look for shader container signatures
p = positions[0]
blob = d[p:p+256]
hex_lines = []
for i in range(0, min(len(blob), 256), 16):
    bts = blob[i:i+16]
    h = ' '.join(f'{b:02x}' for b in bts)
    a = ''.join(chr(b) if 32<=b<=126 else '.' for b in bts)
    marker = ' <-- DXBC' if i == 4 else ''
    hex_lines.append(f'  +{i:04x}: {h}  {a}{marker}')
for line in hex_lines[:8]:
    print(line)

# Check for specific DXBC/DXIL chunk signatures
print()
print('Shader container signatures:')
chunk_sigs = [(b'RDEF','DXBC RDEF'),(b'VERF','DXBC VERF'),(b'OBUF','DXBC OBUF'),
              (b'DXCi','DXIL DXCi1'),(b'dxil','DXIL dxil'),(b'Signat','Signatures')]
for chunk, name in chunk_sigs:
    c = d.count(chunk)
    if c > 0: print(f'  {name}: {c}')

# Check for DXBC-style root signatures (RDEF contains shader info)
print()
print('Checking entry[0] raw data:')
raw = d[p:p+64]
h = ' '.join(f'{b:02x}' for b in raw)
a = ''.join(chr(b) if 32<=b<=126 else '.' for b in raw)
print(h)
print(a)

# Check ALL entries for DXBC/DXIL chunk signatures within their payload
print()
print('DXBC-style chunks found across all entries:')
for chunk, name in [(b'RDEF','RDEF'),(b'OBUF','OBUF'),(b'DXCi','DXCi1'),(b'dxil','dxil'),(b'VERF','VERF')]:
    c = 0
    for pos in positions[:200]:
        if d[pos:pos+512].count(chunk) > 0:
            c += 1
    print(f'  {name}: in {c} entries')
