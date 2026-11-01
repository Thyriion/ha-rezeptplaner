#!/usr/bin/env python3
"""Static checks for the vanilla-JS frontend (no bundler, no node needed for the first three).

1. Every name imported from './x.js' is exported by x.js.
2. Every name in app.js's `Object.assign(window, {...})` is imported or defined there.
3. Every function called from an inline `on…="…"` handler (in index.html or JS templates)
   is exposed on `window`.
4. If `node` is available, every module passes `node --check`.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "rezeptplaner" / "frontend"
BUILTIN_CALLS = {"if", "for", "while", "switch", "function", "return", "confirm", "alert", "prompt"}

errors: list[str] = []
sources = {p.name: p.read_text(encoding="utf8") for p in sorted(FRONTEND.glob("*.js"))}


def exports_of(text: str) -> set[str]:
    names = set(re.findall(r"export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", text))
    for block in re.findall(r"export\s*\{([^}]*)\}", text):
        names |= {part.split(" as ")[-1].strip() for part in block.split(",") if part.strip()}
    return names


# 1. imports resolve
for fname, text in sources.items():
    for names, target in re.findall(r"import\s*\{([^}]*)\}\s*from\s*'\./([\w.-]+)'", text):
        if target not in sources:
            errors.append(f"{fname}: imports from missing module {target}")
            continue
        available = exports_of(sources[target])
        for name in (n.split(" as ")[0].strip() for n in names.split(",") if n.strip()):
            if name not in available:
                errors.append(f"{fname}: '{name}' is not exported by {target}")

# 2. window exposure in app.js
app = sources.get("app.js", "")
exposed: set[str] = set()
match = re.search(r"Object\.assign\(window,\s*\{(.*?)\}\);", app, re.DOTALL)
if match:
    exposed = set(re.findall(r"[A-Za-z_$][\w$]*", re.sub(r"//.*", "", match.group(1))))
    imported = set()
    for names in re.findall(r"import\s*\{([^}]*)\}", app):
        imported |= {n.split(" as ")[-1].strip() for n in names.split(",") if n.strip()}
    local = set(re.findall(r"(?:function|const|let)\s+([A-Za-z_$][\w$]*)", app))
    for name in sorted(exposed - imported - local):
        errors.append(f"app.js: '{name}' is exposed on window but neither imported nor defined")
else:
    errors.append("app.js: Object.assign(window, {...}) block not found")

# 3. inline handlers call only exposed functions
handler_sources = {"index.html": (FRONTEND / "index.html").read_text(encoding="utf8"), **sources}
for fname, text in handler_sources.items():
    for handler in re.findall(r"\bon[a-z]+=\"([^\"]*)\"", text):
        handler = re.sub(r"\$\{[^}]*\}", "0", handler)
        for call in re.findall(r"(?<![\w.$])([A-Za-z_$][\w$]*)\(", handler):
            if call not in exposed and call not in BUILTIN_CALLS:
                errors.append(f"{fname}: inline handler calls '{call}()' which is not exposed on window")

# 4. syntax
node = shutil.which("node")
if node:
    with tempfile.TemporaryDirectory() as tmp:
        for fname, text in sources.items():
            copy = Path(tmp) / (fname[:-3] + ".mjs")
            copy.write_text(text, encoding="utf8")
            result = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True)
            if result.returncode:
                errors.append(f"{fname}: syntax error\n{result.stderr.strip()}")
else:
    print("note: node not found, skipping syntax check")

if errors:
    print("\n".join(f"FAIL {e}" for e in errors))
    sys.exit(1)
print(f"frontend OK ({len(sources)} modules, {len(exposed)} window handlers)")
