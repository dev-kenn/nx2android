#!/usr/bin/env python3
"""Build lsfg_bench for arm64 Android with the NDK's clang.  build.py [--ndk DIR] [--api 31] [--out FILE]"""
import argparse, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--ndk', default=os.environ.get('ANDROID_NDK_HOME') or r'C:\Users\Kenn\AppData\Roaming\nx2android\toolchains\android-ndk-r27c')
ap.add_argument('--api', default='31')
ap.add_argument('--out', default=str(HERE / 'build' / 'lsfg_bench'))
a = ap.parse_args()

host = {'nt': 'windows-x86_64', 'posix': 'darwin-x86_64' if sys.platform == 'darwin' else 'linux-x86_64'}[os.name]
bin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'
cc = bin_ / ('clang.exe' if os.name == 'nt' else 'clang')
out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
cmd = [str(cc), f'--target=aarch64-linux-android{a.api}', '-O2', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-std=gnu11',
       str(HERE / 'lsfg_bench.c'), '-o', str(out), '-lvulkan', '-lm']
print(' '.join(cmd))
sys.exit(subprocess.run(cmd).returncode)
