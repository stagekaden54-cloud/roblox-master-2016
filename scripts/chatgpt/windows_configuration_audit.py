#!/usr/bin/env python3
"""Configuration-aware inventory for the legacy Windows client (no compilation)."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = [ROOT / "WindowsClient/WindowsClient.vcxproj",
            ROOT / "Base/Base.vcxproj",
            ROOT / "App/ App.vcxproj"]
CONFIG = "Debug|Win32"
SOURCE_EXTS = {".h", ".hpp", ".hh", ".cpp", ".c", ".cc", ".inl"}

def local(tag):
    return tag.rsplit("}", 1)[-1]

def text_of(node):
    return "".join(node.itertext()).strip()

def condition_matches(value):
    """Evaluate common MSBuild configuration/platform equality conditions conservatively."""
    if not value:
        return True
    v = value.strip()
    pairs = re.findall(r"""['"]\$\(Configuration\)\|\$\(Platform\)['"]\s*==\s*['"]([^'"]+)['"]""", v, re.I)
    if pairs:
        return any(x.lower() == CONFIG.lower() for x in pairs)
    configs = re.findall(r"""['"]\$\(Configuration\)['"]\s*==\s*['"]([^'"]+)['"]""", v, re.I)
    if configs:
        return any(x.lower() == CONFIG.split("|")[0].lower() for x in configs)
    platforms = re.findall(r"""['"]\$\(Platform\)['"]\s*==\s*['"]([^'"]+)['"]""", v, re.I)
    if platforms:
        return any(x.lower() == CONFIG.split("|")[1].lower() for x in platforms)
    # Unknown conditions are retained for review, not assumed to be active.
    return False

def project_inventory(path):
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "error": "project file not found"}
    tree = ET.parse(path)
    root = tree.getroot()
    out = {"path": str(path.relative_to(ROOT)), "imports": [], "project_references": [],
           "active_property_groups": [], "active_item_definitions": []}
    for node in root.iter():
        tag = local(node.tag)
        cond = node.attrib.get("Condition", "")
        if tag == "Import":
            out["imports"].append({"project": node.attrib.get("Project"), "condition": cond,
                                   "condition_matches_debug_win32": condition_matches(cond)})
        elif tag == "ProjectReference":
            out["project_references"].append({"include": node.attrib.get("Include"), "condition": cond,
                                              "condition_matches_debug_win32": condition_matches(cond)})
        elif tag in ("PropertyGroup", "ItemDefinitionGroup"):
            entry = {"condition": cond, "condition_matches_debug_win32": condition_matches(cond), "values": {}}
            for child in node:
                entry["values"][local(child.tag)] = text_of(child)
            out["active_property_groups" if tag == "PropertyGroup" else "active_item_definitions"].append(entry)
    return out

def resolve_project_reference(project_path, include):
    """Resolve MSBuild Windows-style paths and expose failures instead of dropping them."""
    normalized = include.replace("\\", "/")
    candidate = (project_path.parent / normalized).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None, "outside_repository"
    if candidate.exists():
        return candidate, "resolved"
    # GitHub-hosted Windows builds are case-insensitive; this fallback also makes
    # local Linux runs behave consistently when a legacy include has casing drift.
    current = ROOT.resolve()
    try:
        relative = candidate.relative_to(current)
    except ValueError:
        return None, "outside_repository"
    for part in relative.parts:
        if not current.is_dir():
            return None, "missing_path_component"
        matches = [p for p in current.iterdir() if p.name.lower() == part.lower()]
        if len(matches) != 1:
            return None, "missing_or_ambiguous_path_component"
        current = matches[0]
    return (current, "resolved") if current.exists() else (None, "missing_file")


def project_graph(start_paths):
    """Follow active repository-local ProjectReference edges and retain resolution diagnostics."""
    queue = list(start_paths)
    seen = set()
    results = []
    while queue:
        path = queue.pop(0).resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            item = project_inventory(path)
        except ET.ParseError as e:
            item = {"path": str(path.relative_to(ROOT)), "xml_error": str(e)}
        results.append(item)
        for ref in item.get("project_references", []):
            if not ref.get("condition_matches_debug_win32"):
                continue
            include = ref.get("include")
            if not include or "$(" in include:
                ref["resolution"] = "property_based_path_not_resolved"
                continue
            child, status = resolve_project_reference(path, include)
            ref["resolution"] = status
            ref["resolved_path"] = child.relative_to(ROOT).as_posix() if child else None
            if child and child.suffix.lower() == ".vcxproj" and child not in seen:
                queue.append(child)
    return results

def scan_sources():
    hits = {k: [] for k in ("tbb_includes", "telemetry_mentions", "vmprotect_mentions", "vmprotect_guards")}
    patterns = {
        "tbb_includes": re.compile(r"#\s*include\s*[<\"]tbb/[^>\"]+[>\"]|#\s*include\s*[<\"]tbb\.h[>\"]", re.I),
        "telemetry_mentions": re.compile(r"Telemetry2SDK|TelemetryClient|Telemetry", re.I),
        "vmprotect_mentions": re.compile(r"VMProtectSDK\.h|VMProtect[A-Za-z0-9_]*\s*\(", re.I),
        "vmprotect_guards": re.compile(r"^\s*#\s*(?:if|ifdef|ifndef|elif).*(?:VMProtect|VMP)", re.I|re.M),
    }
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SOURCE_EXTS:
            continue
        if any(part in {".git", "packages", "node_modules"} for part in p.parts):
            continue
        try: data = p.read_text(encoding="utf-8", errors="ignore")
        except OSError: continue
        rel = str(p.relative_to(ROOT))
        for key, pat in patterns.items():
            for m in pat.finditer(data):
                line = data.count("\n", 0, m.start()) + 1
                item = {"file": rel, "line": line, "match": m.group(0).strip()[:180]}
                if item not in hits[key]: hits[key].append(item)
    return hits

def scan_build_metadata():
    """Find dependency tokens in project/build metadata as well as C++ source."""
    patterns = re.compile(r"TBB|Telemetry|VMProtect|DSBaseClasses|DirectShow", re.I)
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".vcxproj", ".props", ".targets"}:
            continue
        if any(part in {".git", "packages", "node_modules"} for part in p.parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if patterns.search(line):
                hits.append({"file": p.relative_to(ROOT).as_posix(), "line": number,
                             "text": line.strip()[:240]})
    return hits


def main():
    projects = project_graph([ROOT / "WindowsClient/WindowsClient.vcxproj"])
    result = {
        "audit_type": "static configuration-aware inventory; not a build",
        "configuration": CONFIG,
        "solution": "Client_2012.sln",
        "target_project": "WindowsClient/WindowsClient.vcxproj",
        "expected_output": "RobloxPlayerBetaRaw.exe",
        "project_inventory": projects,
        "source_reference_scan": scan_sources(),
        "build_metadata_dependency_scan": scan_build_metadata(),
        "limitations": [
            "MSBuild property expansion and imported .props/.targets evaluation are not performed.",
            "Preprocessor branches are reported, not evaluated by a compiler.",
            "Project-reference resolution is repository-local and does not evaluate MSBuild property-based paths or imported build logic.",
            "A source mention does not prove the file is compiled in Debug|Win32.",
            "No proprietary SDKs are downloaded and no protection features are disabled.",
            "This audit does not compile, link, or produce an executable."
        ]
    }
    dest = ROOT / "windows-configuration-audit.json"
    dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(dest.relative_to(ROOT)),
                      "projects": len(projects),
                      "source_scan_counts": {k: len(v) for k,v in result["source_reference_scan"].items()},
                      "audit_type": result["audit_type"]}, indent=2))
    return 0 if not any("xml_error" in p for p in projects) else 1

if __name__ == "__main__":
    sys.exit(main())
