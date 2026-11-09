#!/usr/bin/env python3
"""Push lsfg_bench and a directory of .spv files to the phone and run it.
run.py [--spv DIR] [--serial R5CTA04NZWN] [--adb PATH] [bench args...]   e.g. run.py --size 1280x720 --runs 10"""
import argparse, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ap = argparse.ArgumentParser()
ap.add_argument('--spv', default=str(ROOT / '.gamedump/LosslessLSFG/spirv/shaders'))
ap.add_argument('--serial', default='R5CTA04NZWN')
ap.add_argument('--adb', default='adb')
ap.add_argument('--bin', default=str(HERE / 'build' / 'lsfg_bench'))
ap.add_argument('--remote', default='/data/local/tmp/lsfg_bench')
a, rest = ap.parse_known_args()

adb = [a.adb, '-s', a.serial]
def run(args, **kw):
    print('>', ' '.join(args), flush=True)
    return subprocess.run(adb + args, **kw)

if not Path(a.bin).exists():
    sys.exit(f'{a.bin} missing: run build.py first')
if not Path(a.spv).is_dir():
    sys.exit(f'{a.spv} is not a directory')
run(['shell', 'rm', '-rf', a.remote]).check_returncode()
run(['shell', 'mkdir', '-p', a.remote + '/spv']).check_returncode()
run(['push', a.bin, a.remote + '/lsfg_bench']).check_returncode()
run(['push', a.spv + '/.', a.remote + '/spv/']).check_returncode()
run(['shell', 'chmod', '755', a.remote + '/lsfg_bench']).check_returncode()
r = run(['shell', f'cd {a.remote} && ./lsfg_bench spv ' + ' '.join(rest)])
sys.exit(r.returncode)
