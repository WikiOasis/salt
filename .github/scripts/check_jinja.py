import subprocess
import sys

import jinja2

env = jinja2.Environment(extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])
files = subprocess.run(
    ["git", "ls-files", "*.jinja", "*.sls", "*.sls.example"],
    check=True,
    capture_output=True,
    text=True,
).stdout.split()

failed = 0
for path in files:
    try:
        with open(path, encoding="utf-8") as handle:
            env.parse(handle.read())
    except jinja2.TemplateSyntaxError as exc:
        failed += 1
        print(f"::error file={path},line={exc.lineno}::{exc.message}")

print(f"checked {len(files)} files, {failed} failed")
sys.exit(1 if failed else 0)
