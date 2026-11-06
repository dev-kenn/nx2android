d = open('Lossless.dll','rb').read()
off = 0
positions = []
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    positions.append(i)
    off = i + 1

print(f'Found {len(positions)} DXBC markers')
print('First 5 entries (64 bytes after marker):')
for pos in positions[:5]:
    print(f'@{pos:#08x}:', ' '.join(f'{b:02x}' for b in d[pos:pos+64]))

from collections import Counter
hs_count = Counter()
ts_count = Counter()
for pos in positions:
    hs = int.from_bytes(d[pos+4:pos+8], 'little')
    ts = int.from_bytes(d[pos+8:pos+12], 'little')
    hs_count[hs] += 1
    ts_count[ts] += 1

print()
print('Header size distribution:')
for k,v in sorted(hs_count.items())[:10]:
    print(f'  hdr=0x{k:X}: {v} occurrences')

print('Total size distribution:')
for k,v in sorted(ts_count.items())[:10]:
    print(f'  tot=0x{k:X}: {v} occurrences')

# Check inter-DXBC spacing
diffs = [positions[j+1]-positions[j] for j in range(min(len(positions)-1,50))]
print(f'First 20 diffs: {diffs[:20]}')
print(f'Unique diffs: {sorted(set(diffs[:30]))}')

# Check if any DXBC is valid (hdr in [0x1C, 0x2000), total > hdr, fits)
valid = []
for pos in positions:
    hs = int.from_bytes(d[pos+4:pos+8], 'little')
    ts = int.from_bytes(d[pos+8:pos+12], 'little')
    if 0x1C <= hs < 0x2000 and ts > hs and (pos+ts) <= len(d):
        valid.append(pos)
print(f'Valid DXBC: {len(valid)} (should be 202 if real)')

# SPIR-V check
spv = bytes([0x13,0x02,0x03,0x0f])
sv = d.find(spv)
print(f'SPIR-V magic present: {sv is not None}')
