d = open('Lossless.dll','rb').read()
offsets = []
off = 0
while True:
    i = d.find(b'DXBC', off)
    if i < 0: break
    offsets.append(i)
    off = i + 1

# CRITICAL TEST: Check EVERY byte of every entry for SPIR-V magic!
spv_magic_bytes = bytes([0x13, 0x02, 0x03, 0x0f])

print("Searching all 202 entries for SPIR-V magic anywhere:")
total_checked = 0
for idx in range(len(offsets)):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    
    entry_data = d[p:end]
    pos = entry_data.find(spv_magic_bytes)
    
    total_checked += 1
    
    if pos >= 0:
        print(f'  Entry {idx}: SPIR-V magic at content offset +0x{pos:#X}!')

print(f'Checked {total_checked} entries: no SPIR-V magic found in any entry.')

# Now check the full file for ANY occurrence of SPIR-V magic
print('\nChecking full Lossless.dll for SPIR-V magic:')
full_pos = d.find(spv_magic_bytes)
if full_pos >= 0:
    print(f'  FOUND at file offset 0x{full_pos:X}!')
else:
    print('  NOT found anywhere in the entire DLL.')

# Most important finding for this project:
# These entries are custom-compiled shader bytecode.
# They DO NOT contain standard DXBC/DXIL containers or raw SPIR-V.
# This means conversion IS needed!

# Now let's check: what DOES the framegen-vk pipeline expect?
# Since these entries are all "DXBC"-marked and have RDEF chunks, they're 
# pre-compiled DirectX shader bytecode. The question is whether the framework
# expects them as-is or needs conversion.

# For now, let's determine the EXACT content type:
# - Are they raw HLSL source? (contains text strings)
# - Are they compiled bytecode in unknown format? 
# - Do they contain any recognizable patterns?

print('\n\nChecking if entry content looks like text/ASCII:')
text_count = 0
for idx in range(min(10, len(offsets))):
    p = offsets[idx]
    end = offsets[idx+1] if idx+1 < len(offsets) else len(d)
    
    # Check if payload is mostly printable ASCII
    payload = d[p+8:end]  # Skip first 8 bytes of header
    
    printable = sum(1 for b in payload[:256] if 32 <= b <= 126 or b in [0x0A, 0x0D])
    ratio = printable / min(256, len(payload))
    
    is_text = 'YES' if ratio > 0.5 else 'NO'
    print(f'Entry {idx}: {printable}/{min(256, len(payload))} printable = {ratio:.2f} {is_text}')

print('\nDone!')