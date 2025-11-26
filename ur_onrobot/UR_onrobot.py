#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# UR_onrobot.py — OnRobot (URCap XML-RPC) helper for Universal Robots

from __future__ import annotations
import argparse, sys, time, json, pycurl, xmlrpc.client
from io import BytesIO
from dataclasses import dataclass
from typing import Any, Dict, Optional, Iterable

TIMEOUT_S = 2.5
SENTINELS = {-1, -4, -999}

def _serialize_xmlrpc_value(v: Any) -> str:
    if isinstance(v, bool):   return f"<boolean>{str(v).lower()}</boolean>"
    if isinstance(v, int):    return f"<int>{v}</int>"
    if isinstance(v, float):  return f"<double>{v}</double>"
    return f"<string>{v}</string>"

def _xmlrpc_call(ip: str, method: str, params: Iterable[Any] = (), timeout_s: float = TIMEOUT_S) -> Any:
    body = [
        '<?xml version="1.0"?>', "<methodCall>", f"<methodName>{method}</methodName>", "<params>",
        *[f"<param><value>{_serialize_xmlrpc_value(p)}</value></param>" for p in params], "</params>", "</methodCall>",
    ]
    c, buf = pycurl.Curl(), BytesIO()
    c.setopt(c.URL, f"http://{ip}:41414")
    c.setopt(c.HTTPHEADER, ["Content-Type: application/x-www-form-urlencoded"])
    c.setopt(c.POSTFIELDS, "".join(body).encode())
    c.setopt(c.WRITEDATA, buf)
    c.setopt(c.CONNECTTIMEOUT_MS, int(timeout_s * 1000))
    c.setopt(c.TIMEOUT_MS, int(timeout_s * 1000))
    try:
        c.perform()
        code = c.getinfo(pycurl.RESPONSE_CODE)
    finally:
        c.close()
    resp = buf.getvalue().decode("utf-8")
    if code != 200:
        raise RuntimeError(f"HTTP {code} on {method}: {resp[:200]}")
    vals, _ = xmlrpc.client.loads(resp)
    return vals[0] if vals else None

def _try(ip: str, method: str, params: Iterable[Any] = ()):
    try:
        return True, _xmlrpc_call(ip, method, params)
    except Exception as e:
        return False, e

def _is_real_scalar(v: Any) -> bool:
    try:
        f = float(v)
        return f not in SENTINELS
    except Exception:
        return v not in ("", None)

def _real_in_range(v: Any, lo: float, hi: float) -> bool:
    try:
        f = float(v)
        return (f not in SENTINELS) and (lo < f <= hi)
    except Exception:
        return False

def _ns(name: str) -> str:
    if name.startswith("system."): return "system"
    parts = name.split("_", 1)
    return parts[0] if len(parts) == 2 else "misc"

DANGEROUS_KEYS = ("grip", "move", "release", "stop", "start", "calibrate", "initialize", "home", "set_", "shutdown", "auto_calibrate")
SAFE_HINTS = ("get_", "list", "system.", "capabilities")

def _classify(name: str) -> str:
    lname = name.lower()
    return "danger" if any(k in lname for k in DANGEROUS_KEYS) else "safe" if any(k in lname for k in SAFE_HINTS) else "unknown"

def dump_onrobot_api(ip: str):
    ok, methods = _try(ip, "system.listMethods", ())
    if not ok or not isinstance(methods, (list, tuple)):
        raise RuntimeError(f"{ip}: system.listMethods failed: {methods}")
    methods = sorted(set(methods))
    items = {}
    by_ns = {}
    for m in methods:
        info = {"name": m, "ns": _ns(m), "class": _classify(m)}
        okS, sig = _try(ip, "system.methodSignature", (m,))
        if okS and isinstance(sig, (list, tuple)): info["signature"] = sig
        okH, helptext = _try(ip, "system.methodHelp", (m,))
        if okH and isinstance(helptext, str) and helptext.strip(): info["help"] = helptext.strip()
        items[m] = info
        by_ns.setdefault(info["ns"], []).append(m)
    out = {"ip": ip, "count": len(methods), "by_namespace": {k: sorted(v) for k, v in by_ns.items()}, "items": items}
    for capname in ("system.getCapabilities", "system.capabilities", "get_discovery"):
        okC, cap = _try(ip, capname, ())
        if okC: out.setdefault("capabilities", {})[capname] = cap
    return out

def merge_catalogs(cats):
    cats = list(cats)
    all_methods = set()
    by_ns = {}
    items = {}
    for c in cats:
        all_methods.update(c["items"].keys())
        for k, arr in c["by_namespace"].items():
            by_ns.setdefault(k, set()).update(arr)
        for k, v in c["items"].items():
            items.setdefault(k, {}).update(v)
    return {"ips": [c["ip"] for c in cats], "total_methods": len(all_methods),
            "by_namespace": {k: sorted(list(v)) for k, v in by_ns.items()}, "items": items}

def write_md(catalog, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# OnRobot URCap XML-RPC API ({len(catalog['items'])} methods)\n\n")
        for ns, names in sorted(catalog["by_namespace"].items(), key=lambda kv: kv[0]):
            f.write(f"## `{ns}` ({len(names)})\n")
            for m in names:
                info = catalog["items"][m]; klass = info.get("class", "?")
                sig = info.get("signature"); sigtxt = (" — " + ", ".join(map(str, sig))) if sig else ""
                f.write(f"- `{m}`  _[{klass}]_{sigtxt}\n")
                if "help" in info:
                    ht = info["help"].strip().replace("\n", " ")
                    if len(ht) > 200: ht = ht[:200] + "…"
                    f.write(f"  \n  {ht}\n")
            f.write("\n")

from dataclasses import dataclass
@dataclass
class Meta:
    family: str
    ns: str
    gid: int
    wmin: float
    wmax: float
    fmax: int

def _detect_fg(ip: str, gid: int) -> Optional[Meta]:
    ok_w, _ = _try(ip, "fgp_get_external_width", (gid,))
    ok_n, wn = _try(ip, "fgp_get_min_external_width", (gid,))
    ok_x, wx = _try(ip, "fgp_get_max_external_width", (gid,))
    ok_f, fx = _try(ip, "fgp_get_max_force", (gid,))
    if ok_w and ok_n and ok_x and ok_f and _real_in_range(wn, 0, 500) and _real_in_range(wx, 0, 500) and float(wx) > float(wn):
        return Meta("FG", "fgp", gid, float(wn), float(wx), int(float(fx)))
    ok_w, _ = _try(ip, "twofg_get_external_width", (gid,))
    ok_n, wn = _try(ip, "twofg_get_min_external_width", (gid,))
    ok_x, wx = _try(ip, "twofg_get_max_external_width", (gid,))
    ok_f, fx = _try(ip, "twofg_get_max_force", (gid,))
    if ok_w and ok_n and ok_x and ok_f and _real_in_range(wn, 0, 500) and _real_in_range(wx, 0, 500) and float(wx) > float(wn):
        return Meta("FG", "twofg", gid, float(wn), float(wx), int(float(fx)))
    return None

def _detect_rg(ip: str, gid: int) -> Optional[Meta]:
    ok_w, w = _try(ip, "rg_get_width", (gid,))
    ok_s, s = _try(ip, "rg_get_status", (gid,))
    if ok_w and _is_real_scalar(w) and ok_s:
        try:
            if int(s) in (-1,):  return None
        except Exception:
            pass
        return Meta("RG", "rg", gid, 0.0, 110.0, 40)
    return None

def _detect_vg(ip: str, gid: int) -> Optional[Meta]:
    ok_v, v = _try(ip, "fgp_get_vg_vacuum_percent", (gid,))
    if ok_v and _is_real_scalar(v): return Meta("VG", "fgp_vg", gid, 0.0, 100.0, 100)
    ok_v10, vac10 = _try(ip, "vg10_get_vacuum", (gid,))
    if ok_v10 and _is_real_scalar(vac10): return Meta("VG", "vg10", gid, 0.0, 100.0, 100)
    ok_a, va = _try(ip, "vgp30_get_vacuum_a_percent", (gid,))
    ok_b, vb = _try(ip, "vgp30_get_vacuum_b_percent", (gid,))
    if (ok_a and _is_real_scalar(va)) or (ok_b and _is_real_scalar(vb)):
        return Meta("VG", "vgp30", gid, 0.0, 100.0, 100)
    return None

def discover(ip: str, gid_candidates=range(0,4)) -> Meta:
    for gid in gid_candidates:
        fg = _detect_fg(ip, gid)
        if fg: return fg
    for gid in gid_candidates:
        rg = _detect_rg(ip, gid)
        if rg: return rg
    for gid in gid_candidates:
        vg = _detect_vg(ip, gid)
        if vg: return vg
    raise RuntimeError(f"No FG/RG/VG gripper detected on {ip} (ids tried: {list(gid_candidates)})")

class UniversalGripper:
    def __init__(self, ip: str, meta: Meta):
        self.ip, self.meta = ip, meta
        self.family, self.ns, self.gid = meta.family, meta.ns, meta.gid
        self.wmin, self.wmax, self.fmax = meta.wmin, meta.wmax, meta.fmax
        if self.family == "FG":
            p = "fgp_" if self.ns == "fgp" else "twofg_"
            self.m_busy   = f"{p}get_busy"
            self.m_gripdet= f"{p}get_grip_detected"
            self.m_status = f"{p}get_status"
            self.m_width  = f"{p}get_external_width"
            self.m_grip   = f"{p}grip_external"
        elif self.family == "RG":
            self.m_busy   = "rg_get_busy"
            self.m_gripdet= "rg_get_grip_detected"
            self.m_status = "rg_get_status"
            self.m_width  = "rg_get_width"
            self.m_grip   = "rg_grip"
            self.m_stop   = "rg_stop"
            self.m_calib  = "rg_calibration"
            self.m_set_tip= "rg_set_fingertip_offset"
        else:
            if self.ns == "fgp_vg":
                self.v_get_pct, self.v_grip, self.v_release = "fgp_get_vg_vacuum_percent", "fgp_vg_grip", "fgp_vg_release"
            elif self.ns == "vg10":
                self.v_get_vac, self.v_grip, self.v_release = "vg10_get_vacuum", "vg10_grip", "vg10_release"
            else:
                self.v_get_pctA, self.v_get_pctB = "vgp30_get_vacuum_a_percent", "vgp30_get_vacuum_b_percent"
                self.v_grip, self.v_release = "vgp30_grip", "vgp30_release"

    # --- RG safety helpers -------------------------------------------------
    def safety_buttons(self) -> dict:
        """Return RG safety states; empty dict for non-RG."""
        if self.family != "RG":
            return {}
        keys = (
            "rg_get_s1_pushed",
            "rg_get_s1_triggered",
            "rg_get_s2_pushed",
            "rg_get_s2_triggered",
            "rg_get_safety_failed",
        )
        out = {}
        for k in keys:
            ok, v = _try(self.ip, k, (self.gid,))
            out[k.replace("rg_get_", "")] = bool(v) if ok and _is_real_scalar(v) else False
        return out

    def safety_ok(self) -> bool:
        """True when no safety trigger/fail is active (RG only)."""
        s = self.safety_buttons()
        return not (s.get("s1_triggered") or s.get("s2_triggered") or s.get("safety_failed"))

    def safety_stop(self):
        """Issue a stop to RG (no-op on others)."""
        if self.family == "RG":
            _try(self.ip, "rg_stop", (self.gid,))

    def set_width_force(self, width_mm: float, force: float = 30, speed: int = 50) -> None:
        if self.family not in ("FG", "RG"):
            raise RuntimeError("set_width_force is only for FG/RG; use set_vacuum for VG.")
        width_mm = max(self.wmin, min(self.wmax, float(width_mm)))
        f = float(max(1.0, min(float(self.fmax), float(force))))
        if self.family == "FG":
            sp = int(max(1, min(100, int(speed))))
            if self.ns == "fgp":
                _xmlrpc_call(self.ip, self.m_grip, (self.gid, float(width_mm), float(f), int(sp)))
            else:
                _xmlrpc_call(self.ip, self.m_grip, (self.gid, float(width_mm), int(f), int(sp)))
        else:
            _xmlrpc_call(self.ip, self.m_grip, (self.gid, float(width_mm), float(f)))

    def set_vacuum(self, a_percent: Optional[int] = None, b_percent: Optional[int] = None):
        if self.family != "VG": raise RuntimeError("Not a vacuum gripper.")
        if self.ns == "fgp_vg":
            a = int(0 if a_percent is None else max(0, min(100, int(a_percent))))
            b = int(0 if b_percent is None else max(0, min(100, int(b_percent))))
            _xmlrpc_call(self.ip, self.v_grip, (self.gid, a, b))
        elif self.ns == "vg10":
            if a_percent is not None and b_percent is not None:
                pct = max(0, min(100, int((int(a_percent) + int(b_percent)) / 2)))
                _xmlrpc_call(self.ip, self.v_grip, (self.gid, 2, float(pct)))
            elif a_percent is not None:
                _xmlrpc_call(self.ip, self.v_grip, (self.gid, 0, float(max(0, min(100, int(a_percent))))))
            elif b_percent is not None:
                _xmlrpc_call(self.ip, self.v_grip, (self.gid, 1, float(max(0, min(100, int(b_percent))))))
        else:
            a = int(0 if a_percent is None else max(0, min(100, int(a_percent))))
            b = int(0 if b_percent is None else max(0, min(100, int(b_percent))))
            _xmlrpc_call(self.ip, self.v_grip, (self.gid, a, b))

    def release(self, a: bool = True, b: bool = True):
        if self.family != "VG": raise RuntimeError("Not a vacuum gripper.")
        if self.ns == "fgp_vg":
            _xmlrpc_call(self.ip, self.v_release, (self.gid, int(a), int(b)))
        elif self.ns == "vg10":
            _xmlrpc_call(self.ip, self.v_release, (self.gid, bool(a), bool(b)))
        else:
            _xmlrpc_call(self.ip, self.v_release, (self.gid, int(a), int(b)))

    def get_width(self) -> float:
        if self.family == "VG": return float("nan")
        ok, v = _try(self.ip, self.m_width, (self.gid,))
        try: return float(v) if ok and _is_real_scalar(v) else float("nan")
        except Exception: return float("nan")

    def get_vacuum(self):
        if self.family != "VG": return None
        if self.ns == "fgp_vg":
            ok, v = _try(self.ip, self.v_get_pct, (self.gid,))
            return v if ok else None
        elif self.ns == "vg10":
            ok, v = _try(self.ip, self.v_get_vac, (self.gid,))
            return v if ok else None
        else:
            okA, a = _try(self.ip, self.v_get_pctA, (self.gid,))
            okB, b = _try(self.ip, self.v_get_pctB, (self.gid,))
            out = {}
            if okA and _is_real_scalar(a): out["A"] = float(a)
            if okB and _is_real_scalar(b): out["B"] = float(b)
            return out

    def is_busy(self) -> bool:
        if self.family == "VG":
            if self.ns == "fgp_vg":
                ok, b = _try(self.ip, "fgp_get_busy", (self.gid,))
                return bool(b) if ok and _is_real_scalar(b) else False
            return False
        ok, v = _try(self.ip, self.m_busy, (self.gid,))
        if ok and _is_real_scalar(v): return bool(v)
        w1 = self.get_width(); time.sleep(0.05); w2 = self.get_width()
        if any(map(lambda x: x != x, (w1, w2))): return False
        return abs(w2 - w1) > 0.2

    def object_detected(self) -> bool:
        if self.family == "VG":
            if self.ns == "fgp_vg":
                ok, gs = _try(self.ip, "fgp_get_vg_grip_status", (self.gid,))
                return bool(gs) if ok and _is_real_scalar(gs) else False
            vac = self.get_vacuum()
            try:
                if isinstance(vac, dict):
                    return max(vac.get("A", 0), vac.get("B", 0)) > 20
            except Exception:
                pass
            return False
        ok, v = _try(self.ip, self.m_gripdet, (self.gid,))
        return bool(v) if ok and _is_real_scalar(v) else False

    def status(self) -> int:
        if self.family == "VG":
            return 1 if self.object_detected() else 0
        ok, v = _try(self.ip, self.m_status, (self.gid,))
        if ok and _is_real_scalar(v):
            try: return int(v)
            except Exception: return 0
        return 2 if self.object_detected() else 0

    def limits(self) -> Dict[str, float]:
        if self.family == "VG":
            return {"vacuum_percent_min": 0, "vacuum_percent_max": 100}
        return {"width_min": self.wmin, "width_max": self.wmax, "force_max": self.fmax}

    def stop(self):
        if self.family != "RG": return None
        ok, v = _try(self.ip, "rg_stop", (self.gid,))
        return v if ok else None

    def calibrate(self):
        if self.family != "RG": return None
        ok, v = _try(self.ip, "rg_calibration", (self.gid, float(0.0)))
        return v if ok else None

    def set_fingertip_offset(self, mm: float):
        if self.family != "RG": return None
        ok, v = _try(self.ip, "rg_set_fingertip_offset", (self.gid, float(mm)))
        return v if ok else None

def make_universal(ip: str, gid_candidates=range(0,4)) -> "UniversalGripper":
    return UniversalGripper(ip, discover(ip, gid_candidates))

def snapshot(g: "UniversalGripper") -> str:
    if g.family == "VG":
        return f"{g.ip}: family=VG ns={g.ns} gid={g.gid} vacuum={g.get_vacuum()} busy={g.is_busy()} status={g.status()} limits={g.limits()}"
    w = g.get_width()
    return f"{g.ip}: family={g.family} ns={g.ns} gid={g.gid} width={w:.3f} busy={g.is_busy()} object={g.object_detected()} status={g.status()} limits={g.limits()}"

def _parse_vac_arg(s: str):
    a = b = None
    for part in s.split(","):
        part = part.strip()
        if not part: continue
        if part.upper().startswith("A="): a = int(part.split("=", 1)[1])
        elif part.upper().startswith("B="): b = int(part.split("=", 1)[1])
    return a, b

def _parse_release_arg(s: str):
    s = s.upper().replace(" ", "")
    return ("A" in s, "B" in s)

def _default_paths(ips):
    base = "onrobot_api"
    if len(ips) == 1: base = f"{base}_{ips[0].replace('.', '_')}"
    return f"{base}.json", f"{base}.md"

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="OnRobot (URCap) helper: dump API + universal gripper")
    ap.add_argument("ips", nargs="+", help="UR controller IP(s)")
    ap.add_argument("--gid", type=int, default=None, help="Gripper id (default: auto 0..3)")
    ap.add_argument("--no-dump", action="store_true", help="Skip writing JSON/MD API reports")
    ap.add_argument("--json", type=str, default=None, help="JSON output path")
    ap.add_argument("--md", type=str, default=None, help="Markdown output path")
    ap.add_argument("--move", action="store_true", help="Send FG/RG move (DANGER)")
    ap.add_argument("--width", type=float, default=30.0, help="Target width in mm (FG/RG)")
    ap.add_argument("--force", type=float, default=30.0, help="Target force (FG/RG)")
    ap.add_argument("--speed", type=int, default=50, help="Speed percent (FG only)")
    ap.add_argument("--vac", type=str, default=None, help="Set vacuum e.g. 'A=60,B=40' (VG only)")
    ap.add_argument("--release", type=str, default=None, help="Release 'A', 'B', or 'A,B' (VG only)")
    args = ap.parse_args(argv)

    cats = []
    for ip in args.ips:
        try:
            print(f"[+] Introspecting {ip} ...")
            cats.append(dump_onrobot_api(ip))
            print(f"    methods: {cats[-1]['count']}; namespaces: {', '.join(sorted(cats[-1]['by_namespace'].keys()))}")
        except Exception as e:
            print(f"    ERROR: {e}")

    if cats and not args.no_dump:
        merged = merge_catalogs(cats)
        json_path, md_path = (args.json, args.md)
        if json_path is None or md_path is None:
            jdef, mdef = _default_paths(args.ips)
            json_path = json_path or jdef
            md_path   = md_path   or mdef
        with open(json_path, "w", encoding="utf-8") as jf: json.dump(merged, jf, indent=2, ensure_ascii=False)
        write_md(merged, md_path)
        print(f"[✓] Wrote {json_path} and {md_path} (total methods: {merged['total_methods']})")

    rc = 0
    gids = range(args.gid, args.gid + 1) if args.gid is not None else range(0, 4)
    for ip in args.ips:
        try:
            g = make_universal(ip, gids)
            print("SNAPSHOT:", snapshot(g))
            if args.vac is not None:
                if g.family == "VG":
                    a, b = _parse_vac_arg(args.vac)
                    print(f"  set_vacuum A={a} B={b}")
                    g.set_vacuum(a, b); time.sleep(0.3); print("  after:", snapshot(g))
                else:
                    print("  [skip] --vac requires VG")
            if args.release is not None:
                if g.family == "VG":
                    ra, rb = _parse_release_arg(args.release)
                    print(f"  release A={ra} B={rb}")
                    g.release(ra, rb); time.sleep(0.3); print("  after:", snapshot(g))
                else:
                    print("  [skip] --release requires VG")
            if args.move:
                if g.family in ("FG", "RG"):
                    print(f"  move width={args.width} force={args.force} speed={args.speed}")
                    g.set_width_force(args.width, args.force, args.speed); time.sleep(0.3); print("  after:", snapshot(g))
                else:
                    print("  [skip] --move not valid for VG")
        except Exception as e:
            rc = 1
            print(f"{ip}: ERROR: {e}")
    return rc

if __name__ == "__main__":
    sys.exit(main())
