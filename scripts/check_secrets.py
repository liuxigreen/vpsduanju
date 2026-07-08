#!/usr/bin/env python3
import json, os
from pathlib import Path

p = Path.home() / '.hermes' / 'duanju' / 'secrets'
print(f"Secrets dir: {p}")
print(f"Exists: {p.exists()}")
if p.exists():
    files = list(p.iterdir())
    print(f"Files: {files}")
    for f in sorted(files):
        print(f"--- {f.name} ---")
        print(f.read_text()[:200])
else:
    print("Secrets directory does not exist.")