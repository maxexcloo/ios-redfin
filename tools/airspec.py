#!/usr/bin/env python3
"""airspec.py: specialise one AIR function of a metallib with Metal function constants, then optimise.
  airspec.py LIB FUNCTION OUT.ll [name=value ...]     (names with or without "fc_"; vectors "a,b,c")
Constants not given count as undefined (air.is_function_constant_defined -> false). The function's
static initialiser (section "air.static_init", which derives globals from the constants) runs at entry.
Needs Homebrew LLVM (llvm-dis, llvm-as, opt).
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import metallib

LLVM = "/opt/homebrew/opt/llvm/bin/"


def demangle(g):
    m = re.match(r"_Z(\d+)(\w+)", g)
    return m.group(2)[: int(m.group(1))] if m else g


def specialise(ll, func, consts):
    out, inits = [], []
    for line in ll.split("\n"):
        # function constant globals: @_Z18fc_texcoord_count0.MTL_FC_INIT_52_h = ... externally_initialized constant i8 undef, section "air.fc_initializer"
        m = re.match(
            r'(@(_Z\w+)\.MTL_FC_INIT_\d+_\w+) = (.*?)externally_initialized constant (.+?) undef, section "air.fc_initializer"(.*)',
            line,
        )
        if m:
            name, ty = demangle(m.group(2)), m.group(4)
            v = consts.get(name)
            if v is None:
                val = (
                    "zeroinitializer"
                    if ty.startswith("<")
                    else ("0" if ty.startswith("i") else "0.0")
                )
            elif ty.startswith("<"):
                _n, ety = re.match(r"<(\d+) x (\w+)>", ty).groups()
                parts = v.split(",")
                val = "<" + ", ".join(f"{ety} {p}" for p in parts) + ">"
            else:
                val = v
            out.append(f"{m.group(1)} = {m.group(3)}constant {ty} {val}{m.group(5)}")
            continue
        m = re.match(
            r"(\s*%[\w.]+) = (?:tail )?call i1 @air\.is_function_constant_defined\(ptr addrspace\(2\)[^@]*@(_Z\w+)\.MTL_FC_INIT",
            line,
        )
        if m:
            out.append(
                "{} = or i1 {}, false".format(
                    m.group(1), "true" if demangle(m.group(2)) in consts else "false"
                )
            )
            continue
        m = re.match(
            r"(\s*%[\w.]+) = (?:tail )?call (i\d+) @air\.normalize_function_constant_predicate\.i\d+\((i\d+) ([^)]+)\)",
            line,
        )
        if m:
            out.append(f"{m.group(1)} = or {m.group(2)} {m.group(4)}, 0")
            continue
        m = re.match(
            r'define internal void (@[\w.]+)\(\) .*section "air.static_init"', line
        )
        if m:
            inits.append(m.group(1))
        out.append(line)
    text = "\n".join(out)
    # run the static initialisers first thing in the shader function
    m = re.search(rf"(define [^\n]*@{re.escape(func)}\([^\n]*\{{\n)", text)
    assert m, "no function " + func
    calls = "".join(f"  call void {i}()\n" for i in inits)
    text = text[: m.end()] + calls + text[m.end() :]
    # upstream LLVM has no air64 target; the optimiser needs none
    text = re.sub(r'target triple = "air64[^"]*"\n', "", text)
    # the initialiser is no longer run by anyone else: drop it from llvm.global_ctors
    text = re.sub(r"@llvm\.global_ctors = appending global [^\n]*\n", "", text)
    return text


def main():
    lib, func, out = sys.argv[1:4]
    consts = {}
    for a in sys.argv[4:]:
        k, v = a.split("=", 1)
        consts[k if k.startswith("fc_") else "fc_" + k] = v
    d, funcs = metallib.parse(lib)
    f = next(f for f in funcs if f["name"] == func)
    tmp = tempfile.mkdtemp()
    bc = os.path.join(tmp, "f.bc")
    Path(bc).write_bytes(d[f["bc_abs"] : f["bc_abs"] + f["bcsize"]])
    ll = subprocess.run(
        [LLVM + "llvm-dis", bc, "-o", "-"], capture_output=True, text=True, check=True
    ).stdout
    spec = os.path.join(tmp, "spec.ll")
    Path(spec).write_text(specialise(ll, func, consts))
    # Inline everything: air2glsl translates one function (helpers like bicubic_upsample stay calls at O2).
    subprocess.run(
        [
            LLVM + "opt",
            "-S",
            "-passes=default<O2>,globalopt,globaldce",
            "-inline-threshold=100000",
            spec,
            "-o",
            out,
        ],
        check=True,
    )
    n = sum(
        1 for l in Path(out).read_text().splitlines(keepends=True) if l.startswith("  ")
    )
    print(f"{func!s}: {int(n):d} instructions after specialisation")


if __name__ == "__main__":
    main()
