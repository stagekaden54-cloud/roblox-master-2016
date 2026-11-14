import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
out = root / "perplexity-audit"
out.mkdir(exist_ok=True)

def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout

def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2), encoding="utf-8")

files = git("ls-files", "-z").split("\0")
files = [p for p in files if p]
write("tracked-files.json", files)
write("revision.json", {"commit": git("rev-parse", "HEAD").strip(), "branch": git("branch", "--show-current").strip(), "build_attempted": False})
projects = []
errors = []
ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
for name in files:
    if not name.endswith(".vcxproj"):
        continue
    try:
        tree = ET.parse(root / name)
        entries = []
        for node in tree.iter():
            tag = node.tag.split("}")[-1]
            if tag in {"PlatformToolset", "ProjectConfiguration", "ProjectReference", "Import", "ClCompile", "AdditionalIncludeDirectories", "AdditionalLibraryDirectories", "AdditionalDependencies", "PreprocessorDefinitions", "RuntimeLibrary", "Command"}:
                entry = {"tag": tag, "attributes": dict(node.attrib), "text": (node.text or "").strip()}
                if tag == "ProjectReference" and "Include" in node.attrib:
                    target = (root / name).parent / node.attrib["Include"].replace("\\", "/")
                    entry["exists"] = target.is_file()
                entries.append(entry)
        groups = [{"condition": g.get("Condition", ""), "xml": ET.tostring(g, encoding="unicode")} for g in tree.findall("m:ItemDefinitionGroup", ns)]
        projects.append({"path": name, "entries": entries, "configuration_groups": groups})
    except Exception as exc:
        errors.append({"path": name, "error": str(exc)})
write("projects.json", projects)
write("project-parse-errors.json", errors)
solutions = {}
for name in files:
    if name.endswith(".sln"):
        text = (root / name).read_text(encoding="utf-8-sig", errors="replace")
        solutions[name] = [line for line in text.splitlines() if line.startswith("Project(") or "ActiveCfg" in line or "Build.0" in line]
write("solutions.json", solutions)
pattern = re.compile(r"telemetry|VMProtect|TBB_4_1|tbb[/\\]|tbb\w*\.lib|#\s*pragma\s+comment\s*\(\s*lib|strmbasd?\.lib|DxErr9|ROBLOX_BOOST_CONFIGS", re.I)
suffixes = {".c", ".cc", ".cpp", ".h", ".hpp", ".inl", ".props", ".targets", ".vcxproj", ".bat", ".ps1", ".cmake", ".yml"}
hits = []
for name in files:
    path = root / name
    if path.suffix.lower() not in suffixes:
        continue
    for number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        if pattern.search(line):
            hits.append({"path": name, "line": number, "text": line.strip()})
write("dependency-references.json", hits)
vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
if vswhere.is_file():
    result = subprocess.run([str(vswhere), "-all", "-products", "*", "-format", "json"], capture_output=True, text=True)
    (out / "visual-studio.json").write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("vswhere failed")
summary = f"Inventory only: no compilation, linking, or launch test.\nTracked files: {len(files)}\nC++ projects parsed: {len(projects)}\nProject parse failures: {len(errors)}\nDependency-reference matches: {len(hits)}\nRaw XML conditions are recorded, not evaluated.\nNo SDK license-key contents are collected.\n"
(out / "summary.txt").write_text(summary, encoding="utf-8")
print(summary)
if errors:
    raise SystemExit(1)
