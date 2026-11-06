import struct, sys
sys.path.insert(0, "/Users/kennethsuzuki/Documents/Kenn/nx2android")
from porter import lsfg_extract
data = open("Lossless.dll","rb").read()
print(f"DLL: {len(data)} bytes ({len(data)/1024/1024:.1f} MB)")
pe_off = struct.unpack_from("<I", data, 0x3C)[0]
print(f"PE at {pe_off:#x}")
if pe_off+6<len(data):
    print(f"PE sig: {data[pe_off:pe_off+4]}")
    opt_m = struct.unpack_from("<H", data, pe_off+24)[0]
    ns = struct.unpack_from("<H", data, pe_off+4+20)[0]
    print(f"OptMagic={opt_m} 64bit={opt_m==0x20b}  Sections={ns}")
    st=pe_off+28
    for s in range(min(ns,20)):
        so=st+s*40
        nm=bytes(data[so:so+8])
        sn="".join(chr(b) if 32<=b<=126 else "." for b in nm[:8])
        vsz=struct.unpack_from("<I",data,so+16)[0]
        roff=struct.unpack_from("<I",data,so+20)[0]
        rsz=struct.unpack_from("<I",data,so+24)[0]
        print(f"  {sn}: vsz=0x{vsz:X} roff=0x{roff:X} rsz=0x{rsz:X}")

# Scan signatures
for sig,n in [(b"DXBC","DXBC"),(b"DXIL","DXIL"),(b"FxcB","FXC"),(b"FXCD","FXCDdbg"),(b"DxcI","DxcI"),(b"dxi1","dxi1")]:
    c=data.count(sig)
    if c: print(f"  {n}: {c}")

# DXBC validity check
valid=[]
off=0
while True:
    i=data.find(b"DXBC",off)
    if i<0: break
    off=i+1
    if i+16<=len(data):
        n4=int.from_bytes(data[i+4:i+8],"little")
        tot=int.from_bytes(data[i+8:i+12],"little")
        hv=n4>=0x1C and n4<0x2000
        fv=tot>n4 and (tot-i)<=len(data)
        if hv and fv: valid.append((i,n4,tot))
print(f"Valid DXBC candidates: {len(valid)}")
for v in valid[:10]: print(f"  0x{v[0]:X}: hdr=0x{v[1]:X} tot=0x{v[2]:X}")

# Run extractor
from pathlib import Path as P
import tempfile
with tempfile.TemporaryDirectory() as t:
    blobs=lsfg_extract.extract_dll(P("Lossless.dll"),P(t)+"/out")
    print(f"extract_dll found {len(blobs)} blob(s)")
