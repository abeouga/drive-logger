"""KiCad の回路図と Blender のブレッドボードのモデルが、同じつながりかを照合する。

KiCad の回路図（hardware/kicad/ct125_logger/ct125_logger.kicad_sch）からネットリストを書き出し、
Blender のモデルの layout.py の NETS_CLOSED（意図したつながり）と MUST_BE_ISOLATED（つながないピン）を、
hardware/kicad/blender_correspondence.json の対応表で KiCad の端子に読み替えて比べる。
K-Line（ECU）の分は作っていないので比べない。

使い方:
    python hardware/tools/check_blender_nets.py --layout <Blender のモデルの layout.py> [--kicad-cli <kicad-cli>]

案の回路図と案のモデルを比べるときは、回路図と対応表を選ぶ:
    python hardware/tools/check_blender_nets.py --layout <案のモデルの layout.py>         --sch hardware/kicad/ct125_logger_adxl_spi/ct125_logger_adxl_spi.kicad_sch         --map hardware/kicad/blender_correspondence_adxl_spi.json

kicad-cli は、引数・環境変数 KICAD_CLI・PATH の順に探す。一致すれば 0、食い違いがあれば 1 で終わる。
Python の標準ライブラリだけで動く。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
SCH = HW / "kicad" / "ct125_logger" / "ct125_logger.kicad_sch"
MAP = HW / "kicad" / "blender_correspondence.json"


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)

    def groups(self) -> set[frozenset[str]]:
        out: dict[str, set[str]] = {}
        for x in self.parent:
            out.setdefault(self.find(x), set()).add(x)
        return {frozenset(g) for g in out.values()}


def kicad_nets(cli: str, sch: Path) -> dict[str, set[str]]:
    """ネットの名前 → {"U1.R3", ...}"""
    with tempfile.TemporaryDirectory() as tmp:
        net = Path(tmp) / "ct125.xml"
        subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadxml", "-o", str(net), str(sch)],
                       check=True, capture_output=True)
        root = ET.parse(net).getroot()
    nets = {}
    for n in root.iter("net"):
        nets[n.get("name", "").lstrip("/")] = {f'{nd.get("ref")}.{nd.get("pin")}' for nd in n.iter("node")}
    return nets


def load_layout(path: Path, variant: str):
    os.environ["KLINE_VARIANT"] = variant
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("blender_layout", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def to_kicad(term: str, cmap: dict) -> str | None:
    """Blender の端子名を KiCad の ref.pin に読み替える。K-Line など対応の無いものは None。"""
    head, _, rest = term.partition(".")
    if head == "ESP32":
        return f'{cmap["modules"]["ESP32"]["ref"]}.{rest.split(":")[0]}'
    if head in cmap["modules"]:
        m = cmap["modules"][head]
        return f'{m["ref"]}.{m["pins"][rest]}' if rest in m.get("pins", {}) else None
    if head in cmap["parts"]:
        p = cmap["parts"][head]
        return f'{p["ref"]}.{p[rest]}'
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", required=True, type=Path, help="Blender のモデルの layout.py")
    ap.add_argument("--kicad-cli", default=os.environ.get("KICAD_CLI") or shutil.which("kicad-cli") or "kicad-cli")
    ap.add_argument("--sch", type=Path, default=SCH, help="KiCad の回路図（既定は今の配線）")
    ap.add_argument("--map", type=Path, default=MAP, help="対応表（既定は今の配線の分）")
    args = ap.parse_args()

    cmap = json.loads(args.map.read_text(encoding="utf-8-sig"))  # Windows で保存して BOM が付いても読む
    L = load_layout(args.layout, cmap["blender_model"]["variant_for_check"])
    internal = cmap["modules"]["ESP32"]["internal"]
    esp = cmap["modules"]["ESP32"]["ref"]

    # ---- Blender の意図したつながり（K-Line を除く）
    bl = UnionFind()
    bl_named: dict[str, set[str]] = {}
    for name, terms in L.NETS_CLOSED.items():
        if name not in cmap["net_names"]:
            continue  # K_TX・K_RX など
        mapped = [t for t in (to_kicad(x, cmap) for x in terms) if t]
        bl_named[name] = set(mapped)
        for t in mapped:
            bl.find(t)
        for a, b in zip(mapped, mapped[1:]):
            bl.union(a, b)
    isolated = [t for t in (to_kicad(x, cmap) for x in L.MUST_BE_ISOLATED) if t]

    # ---- KiCad のつながり（ボードの中のつながりを足す）
    nets = kicad_nets(args.kicad_cli, args.sch)
    kc = UnionFind()
    for nodes in nets.values():
        nodes = sorted(nodes)
        for t in nodes:
            kc.find(t)
        for a, b in zip(nodes, nodes[1:]):
            kc.union(a, b)
    for grp in internal:
        terms = [f"{esp}.{p}" for p in grp]
        for t in terms:
            kc.find(t)
        for a, b in zip(terms, terms[1:]):
            kc.union(a, b)

    # ---- 比べる
    ok = True
    print(f"Blender のモデル: {L.REVISION if hasattr(L, 'REVISION') else args.layout}（K-Line を除く）")
    print(f"KiCad の回路図: {args.sch.name}")
    print()
    for bname, kname in cmap["net_names"].items():
        want = bl_named.get(bname, set())
        root = kc.find(sorted(want)[0]) if want else None
        got = {t for t in kc.parent if root and kc.find(t) == root}
        if want == got:
            print(f"一致    {bname:13s} ↔ {kname:8s} {len(want)} 端子")
        else:
            ok = False
            print(f"食い違い {bname:13s} ↔ {kname:8s}")
            if want - got:
                print(f"    Blender にだけある: {sorted(want - got)}")
            if got - want:
                print(f"    KiCad にだけある:   {sorted(got - want)}")
    for t in isolated:
        root = kc.find(t)
        others = sorted(x for x in kc.parent if x != t and kc.find(x) == root)
        if others:
            ok = False
            print(f"食い違い {t} は、つながないはずなのに {others} とつながっている")
    print(f"\nつながないピン: {len(isolated)} 本を確かめた")
    print("結果:", "すべて一致" if ok else "食い違いあり")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
