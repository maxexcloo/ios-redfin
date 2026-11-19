#!/usr/bin/env python3
"""The SM7250 (lito) addresses the redfin port hard-codes, read back from a phone's own flattened device tree,
so that they can be cross-checked (the HakiOS vayu port's soc.args convention). Pure Python, no dependencies.

  python3 -I tools/soc-args.py DTB             KEY=VALUE lines (soc.args), each with the DT node it came from
  python3 -I tools/soc-args.py DTB --check     compare with the recorded code values (CODE below):
                                               exit 0 when all agree, 1 on a difference or a node not found
  python3 -I tools/soc-args.py --table         the values the code uses, and where

DTB: /sys/firmware/fdt as tools/redfin-pull-soc.sh pulls it (the live tree ABL hands over). Not Apple's ADT.
Addresses are CPU physical: a node's reg is translated through its parents' `ranges` (empty = identity).

Every CODE row: the key, the value the code uses, where (patch or file), and how the node is found in the DT.
When the code changes an address, change its row here in the same commit.
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdt

# --- the values the code uses ------------------------------------------------------------------------------
# finders: ('compat', REGEX, REG_INDEX)          nodes whose compatible matches
#          ('name', REGEX, REG_INDEX)            nodes whose name (with unit address) matches
#          ('regname', COMPAT_REGEX, REG_NAME)   the reg entry named REG_NAME (reg-names) of a compatible node
#          ('mem', NAME_OR_COMPAT_REGEX, PROP)   the node a phandle property (memory-region, qcom,wlan-msa-...)
#                                                of the matching node points at, its first reg
#          ('parent', COMPAT_REGEX)              the parent of a compatible node (a bus controller)
#          ('hwlock', COMPAT_REGEX)              the TCSR mutex block of a node's `hwlocks`: (base, lock index)
CODE = [
    (
        "smem",
        0x80900000,
        "xnu 0915 SMEM_PHYS; phone/wifi/smem.h SMEM_BASE",
        ("mem", r"^qcom,smem$", "memory-region"),
    ),
    (
        "smem_size",
        0x200000,
        "xnu 0915 SMEM_SIZE",
        ("mem-size", r"^qcom,smem$", "memory-region"),
    ),
    (
        "tcsr_mutex",
        0x1F40000,
        "phone/wifi/smem.c TCSR_MUTEX(n)",
        ("hwlock", r"^qcom,smem$"),
    ),
    (
        "smem_lock",
        0x1F43000,
        "xnu 0915 smem_lock (TCSR mutex + 0x1000 x hwlocks index)",
        ("hwlock-pa", r"^qcom,smem$"),
    ),
    (
        "apps_smmu",
        0x15000000,
        "xnu 0921/0948/0950/0952 SMMU_PA; phone/wifi/radio.c SMMU_PA",
        ("name", r"^apps-smmu@", 0),
    ),
    (
        "aoss_qmp",
        0xC300000,
        "xnu 0915 aoss; phone/wifi/wland.c QMP_RAM",
        ("compat", r"^qcom,qmp-mbox$", 0),
    ),
    (
        "ipcc",
        0x408000,
        "xnu 0915 ipcc; phone/wifi/ipcc.h IPCC_BASE",
        ("compat", r"^qcom,ipcc$", 0),
    ),
    ("tsens0_tm", 0xC263000, "xnu 0960 tsens0 TM", ("compat", r"^qcom,tsens", 1)),
    ("tsens1_tm", 0xC265000, "xnu 0960 tsens1 TM", ("compat", r"^qcom,tsens", 1)),
    ("gpu", 0x3D00000, "xnu 0904 A6_GPU_BASE", ("compat", r"^qcom,kgsl-3d0$", 0)),
    ("gpu_rscc", 0x3DE0000, "xnu 0904 RSCC", ("regname", r"^qcom,kgsl-3d0$", "rscc")),
    ("gpucc", 0x3D90000, "xnu 0904 A6_GPUCC", ("compat", r"gpucc", 0)),
    ("gpu_smmu", 0x3DA0000, "xnu 0904 A6_SMMU", ("name", r"^kgsl-smmu@", 0)),
    (
        "gpu_zap",
        0x8BC15400,
        "xnu 0904 (pil_gpu_region, a620_zap)",
        ("name", r"^pil_gpu_region", 0),
    ),
    (
        "kregistry",
        0xC8000000,
        "xnu 0904 (GPU pool avoids it)",
        ("name", r"^kregistry_mem", 0),
    ),
    (
        "adsp_mem",
        0x89200000,
        "xnu 0915 ADSP_MEMORY",
        ("mem", r"^qcom,lpass@", "memory-region"),
    ),
    (
        "adsp_mem_size",
        0x2800000,
        "xnu 0915 ADSP_MEMORY_SIZE",
        ("mem-size", r"^qcom,lpass@", "memory-region"),
    ),
    (
        "mpss_mem",
        0x8C000000,
        "phone/wifi/wland.c MPSS_PA",
        ("mem", r"^qcom,mss@", "memory-region"),
    ),
    (
        "mpss_mem_size",
        0x11800000,
        "phone/wifi/wland.c MPSS_SIZE",
        ("mem-size", r"^qcom,mss@", "memory-region"),
    ),
    (
        "wlan_msa",
        0x8BA00000,
        "phone/wifi/wlfw.c MSA_PA",
        ("mem", r"^qcom,icnss$", "qcom,wlan-msa-fixed-region"),
    ),
    (
        "wlan_wcss",
        0x18800000,
        "phone/wifi/radio.c WLAN_PA",
        ("compat", r"^qcom,icnss$", 0),
    ),
    (
        "qup0_wrapper",
        0x8C0000,
        "xnu 0981 GU_WRAP_PA; phone/bt/geni.c WRAP0",
        ("compat", r"^qcom,qupv3-geni-se$", 0),
    ),
    (
        "bt_uart_se",
        0x894000,
        "xnu 0981 GU_SE_PA; phone/bt/geni.c SE",
        ("compat", r"^qcom,msm-geni-serial-hs$", 0),
    ),
    (
        "haptics_se",
        0x98C000,
        "xnu 0907 HAP_SE_PA (DRV2624 bus)",
        ("parent", r"^ti,drv2624$"),
    ),
    (
        "gcc",
        0x100000,
        "xnu 0907 HAP_GCC_PA; phone/bt/geni.c GCC",
        ("compat", r"^qcom,gcc-", 0),
    ),
    ("camcc", 0xAD00000, "xnu 0921 CAMCC_PA", ("compat", r"camcc", 0)),
]
# a selector that finds several nodes keeps them all (--check agrees when the code's value is one of them),
# except these: the n-th hit by address (two TSENS controllers; QUP wrapper 0 of two)
NTH = {"tsens0_tm": 0, "tsens1_tm": 1, "qup0_wrapper": 0}


# --- FDT ---------------------------------------------------------------------------------------------------
def parse(blob):
    if len(blob) < 40:
        raise ValueError("too short for an FDT")
    magic = struct.unpack_from(">I", blob)[0]
    if magic != 0xD00DFEED:
        raise ValueError(f"not an FDT (magic {magic:#x})")
    return fdt.parse(blob)


def ncells(node, prop, default):
    c = node.u32s(prop)
    return c[0] if c else default


def num(cells):
    v = 0
    for c in cells:
        v = v << 32 | c
    return v


def translate(node, addr):
    """A child address of node's bus up to a CPU address, through each ancestor's ranges."""
    bus = node.parent
    while bus is not None and bus.parent is not None:
        r = bus.props.get("ranges")
        if r is None:
            return None  # no ranges: not memory-mapped
        if r:
            ca = ncells(bus, "#address-cells", 2)
            pa = ncells(bus.parent, "#address-cells", 2)
            sc = ncells(bus, "#size-cells", 1)
            c, step, hit = bus.u32s("ranges"), ca + pa + sc, None
            for i in range(0, len(c) - step + 1, step):
                child, parent, size = (
                    num(c[i : i + ca]),
                    num(c[i + ca : i + ca + pa]),
                    num(c[i + ca + pa : i + step]),
                )
                if child <= addr < child + size:
                    hit = addr - child + parent
                    break
            if hit is None:
                return None
            addr = hit
        bus = bus.parent
    return addr


def reg_at(node, index):
    """Translate the indexed reg entry without changing its position."""
    if node is None or node.parent is None:
        return None
    regs = node.reg()
    if index < len(regs):
        addr, size = regs[index]
        addr = translate(node, addr)
        if addr is not None:
            return addr, size
    return None


def phandles(root):
    return {
        n.u32s(k)[0]: n
        for n in root.walk()
        for k in ("phandle", "linux,phandle")
        if n.u32s(k)
    }


# --- finding ------------------------------------------------------------------------------------------------
def select(root, rx):
    """Nodes whose name or any compatible matches rx."""
    r = re.compile(rx)
    return [
        n
        for n in root.walk()
        if r.search(n.name) or any(r.search(c) for c in n.strs("compatible"))
    ]


def find(root, ph, how):
    """[(value, where)] for one finder."""
    kind, out = how[0], []
    if kind in ("compat", "name"):
        r = re.compile(how[1])
        for n in root.walk():
            if (kind == "name" and r.search(n.name)) or (
                kind == "compat" and any(r.search(c) for c in n.strs("compatible"))
            ):
                reg = reg_at(n, how[2])
                if reg is not None:
                    addr, size = reg
                    out.append((addr, f"{n.path} reg[{how[2]}] size {size:#x}"))
    elif kind == "regname":
        for n in select(root, how[1]):
            names = n.strs("reg-names")
            if how[2] in names and (reg := reg_at(n, names.index(how[2]))) is not None:
                addr, size = reg
                out.append((addr, f'{n.path} reg "{how[2]}" size {size:#x}'))
    elif kind in ("mem", "mem-size"):
        for n in select(root, how[1]):
            c = n.u32s(how[2])
            t = ph.get(c[0]) if c else None
            reg = reg_at(t, 0)
            if reg is not None:
                out.append(
                    (
                        reg[0] if kind == "mem" else reg[1],
                        f"{n.path} {how[2]} -> {t.path}",
                    )
                )
    elif kind == "parent":
        for n in select(root, how[1]):
            reg = reg_at(n.parent, 0)
            if reg is not None:
                out.append((reg[0], f"{n.parent.path} (bus of {n.name})"))
    elif kind in ("hwlock", "hwlock-pa"):
        for n in select(root, how[1]):
            c = n.u32s("hwlocks")
            t = ph.get(c[0]) if c else None
            if t is None:
                continue
            idx = c[1] if len(c) > 1 else 0
            block = t
            sc = t.u32s(
                "syscon"
            )  # qcom,tcsr-mutex: syscon = <&tcsr_mutex_regs base stride>
            if sc and sc[0] in ph:
                block = ph[sc[0]]
            reg = reg_at(block, 0)
            if reg is None:
                continue
            base = reg[0] + (sc[1] if sc and len(sc) > 1 else 0)
            stride = sc[2] if sc and len(sc) > 2 else 0x1000
            if kind == "hwlock":
                out.append(
                    (base, f"{block.path} (hwlocks of {n.path}, stride {stride:#x})")
                )
            else:
                out.append(
                    (
                        base + stride * idx,
                        f"{block.path} + {stride:#x} x lock {idx} (hwlocks of {n.path})",
                    )
                )
    else:
        raise ValueError(kind)
    out = sorted(set(out))
    return out


def resolve(root):
    ph = phandles(root)
    rows = []
    for key, val, src, how in CODE:
        hits = find(root, ph, how)
        if key in NTH:
            hits = [hits[NTH[key]]] if len(hits) > NTH[key] else []
        rows.append((key, val, src, hits))
    return rows


def main(argv):
    if argv == ["--table"]:
        for key, val, src, how in CODE:
            print(f"{key:14} {val:#12x}  {src}")
        return 0
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1 or any(a not in ("--check",) for a in argv if a.startswith("--")):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        root = parse(Path(args[0]).read_bytes())
    except (OSError, ValueError, struct.error) as e:
        print(f"soc-args: {args[0]}: {e}", file=sys.stderr)
        return 2
    rows = resolve(root)
    if "--check" not in argv:
        print(
            f"# soc-args.py: SoC addresses from {root.strs('model')[:1] or ['(no model)']} "
            f"{root.strs('compatible')[:2]}; KEY=VALUE  # DT node"
        )
        for key, val, src, hits in rows:
            if not hits:
                print(f"# soc_{key}: not found")
            for i, (v, where) in enumerate(hits):
                print(
                    f"soc_{key}{'' if len(hits) == 1 else '.' + str(i)}={v:#x}  # {where}"
                )
        return 0
    bad = 0
    for key, val, src, hits in rows:
        if not hits:
            state, got = "MISSING", "no DT node"
        elif any(v == val for v, _ in hits):
            state, got = "ok", next(w for v, w in hits if v == val)
        else:
            state, got = "DIFF", ", ".join(f"{v:#x} {w}" for v, w in hits)
        bad += state != "ok"
        print(f"{state:7} {key:14} code {val:#11x}  {src}\n        {'':14} dt   {got}")
    print(
        f"soc-args: {len(rows) - bad} of {len(rows)} agree"
        + ("" if not bad else f"; {bad} to look at")
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
