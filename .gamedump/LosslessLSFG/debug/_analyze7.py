# Parse Lossless.dll as a PE file and extract all RT_RCDATA resource entries
d = open('Lossless.dll','rb').read()

pe_off = int.from_bytes(d[0x3C:0x40], 'little')
opt_start = pe_off + 4 + 20

# Resource table RVA/size from optional headers (standard PE32+ layout)
rsrc_rva = int.from_bytes(d[opt_start+0xF8:opt_start+0xFC], 'little')
rsrc_sz  = int.from_bytes(d[opt_start+0xFC:opt_start+0x100], 'little')
print(f'PE offset: 0x{pe_off:X}')
print(f'Opt header start: 0x{opt_start:X}')
print(f'Resource RVA: 0x{rsrc_rva:X} Size: 0x{rsrc_sz:X}')

# Find the section containing resources
sec_count = int.from_bytes(d[pe_off+6:pe_off+8], 'little')
sec_start = pe_off + 24

print(f'Sections: {sec_count}, sec_start: 0x{sec_start:X}')

rsrc_section = None
for i in range(sec_count):
    s_off = sec_start + i*40
    vaddr = int.from_bytes(d[s_off+12:s_off+16], 'little')
    vsize = int.from_bytes(d[s_off+8:s_off+12], 'little')
    foff  = int.from_bytes(d[s_off+16:s_off+20], 'little')
    fsz   = int.from_bytes(d[s_off+20:s_off+24], 'little')
    name  = d[s_off:s_off+8].decode('ascii', errors='replace').strip()
    
    in_range = vaddr <= rsrc_rva < vaddr + vsize
    print(f'  Sec[{i}] {name:8s}: VA=0x{vaddr:06X} FSZ={fsz:5d} FOFF=0x{foff:X} -> RVA 0x{rsrc_rva:X} in_range={in_range}')
    
    if vaddr <= rsrc_rva < vaddr + vsize:
        rsrc_section = (foff, fsz, foff + (rsrc_rva - vaddr))
        print(f'  *** FOUND MATCH at file offset 0x{rsrc_section[2]:X} ***')

if not rsrc_section:
    print('\nResource section NOT found in any PE section!')
else:
    file_off_base, _, file_off_res = rsrc_section
    print(f'\nResource data at file offset: 0x{file_off_res:X}')
    
    # Parse resource directory
    base = file_off_res
    print(f'\n=== Resource Directory (at 0x{base:X}) ===')
    
    def dump_rsrc_tree(foff, indent=0):
        """Parse a resource directory tree node recursively"""
        if foff + 16 > len(d):
            print('  ' * indent + '(out of bounds)'); return
        
        num_entries = int.from_bytes(d[foff+12:foff+14], 'little')
        num_id_entries = int.from_bytes(d[foff+14:foff+16], 'little')
        
        print(f'  ' * indent + f'Dir @ {foff:#08x}: name={num_entries} id={num_id_entries}')
        
        entry_count = num_entries + num_id_entries
        for i in range(entry_count):
            eoff = foff + 16 + i*8
            if eoff + 8 > len(d): break
            
            entry_val = int.from_bytes(d[eoff:eoff+4], 'little')
            next_off  = int.from_bytes(d[eoff+4:eoff+8], 'little')
            
            if entry_val & 0x80000000:
                tag = "SUB-DIR"
            else:
                tag = f'RES ID:{entry_val & 0x7FFFFFFF}'
            
            print(f'  ' * (indent+1) + f'{tag} @{eoff:#08x} -> next@{next_off:#08x}')
    
    dump_rsrc_tree(base, indent=0)

print('\n=== Also: raw resource section data ===')
# The resource section starts at offset 0x6C6DB (from earlier analysis), size 4096 (0x1000)
for start_off in [0x6C6DB, 0x379B7, 0x80533]:
    print(f'At file offset 0x{start_off:X}:')
    if start_off + 100 <= len(d):
        chunk = d[start_off:start_off+20]
        vals = [int.from_bytes(chunk[i:i+4], 'little') for i in range(0, len(chunk), 4)]
        print(f'  Hex: {" ".join(f"{b:02x}" for b in chunk)}')
        print(f'  Uint32: {vals}')
    
    # Parse resource directory
    base = file_off_res
    print(f'\n=== Resource Directory (at 0x{base:X}) ===')
    
    def dump_rsrc_tree(foff, indent=0):
        """Parse a resource directory tree node recursively"""
        if foff + 16 > len(d):
            print('  ' * indent + '(out of bounds)'); return
        
        num_entries = int.from_bytes(d[foff+12:foff+14], 'little')
        num_id_entries = int.from_bytes(d[foff+14:foff+16], 'little')
        
        print(f'  ' * indent + f'Dir @ {foff:#08x}: name={num_entries} id={num_id_entries}')
        
        entry_count = num_entries + num_id_entries
        for i in range(entry_count):
            eoff = foff + 16 + i*8
            if eoff + 8 > len(d): break
            
            entry_val = int.from_bytes(d[eoff:eoff+4], 'little')
            next_off  = int.from_bytes(d[eoff+4:eoff+8], 'little')
            
            if entry_val & 0x80000000:
                # Subdirectory
                tag = "SUB-DIR"
            else:
                tag = f'RES ID:{entry_val}'
            
            print(f'  ' * (indent+1) + f'{tag} @{eoff:#08x} -> next@{next_off:#08x}')
    
    dump_rsrc_tree(base, indent=0)

else:
    print('Resource section NOT found!')
