#!/usr/bin/env python3
"""Quick syntax check on all rask modules."""
import ast
import sys
import glob

files = sorted(glob.glob("rask/**/*.py", recursive=True) +
                glob.glob("examples/*.py") +
                ["main.py"])

errors = []
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            ast.parse(fh.read())
    except SyntaxError as e:
        errors.append((f, e))

print(f"Checked {len(files)} files.")
if errors:
    print(f"\nSyntax errors in {len(errors)} files:")
    for f, e in errors:
        print(f"  {f}:{e.lineno}: {e.msg}")
    sys.exit(1)
print("All files pass syntax check.")
