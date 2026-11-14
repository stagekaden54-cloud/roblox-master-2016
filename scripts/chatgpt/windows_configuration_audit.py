#!/usr/bin/env python3
"""Static Debug|Win32 dependency audit for the legacy Windows client.

This is a conservative MSBuild project-file interpreter, not MSBuild itself.
Unknown conditions and unresolved properties are reported instead of guessed.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = "Debug"
PLATFORM = "Win32"
CONFIG_KEY = f"{CONFIG}|{PLATFORM}"
SOURCE_EXTS = {".c", ".cc", ".cpp", ".cxx"}
HEADER_EXTS = {".h", ".hh", ".hpp", ".hxx", ".inl"}
SKIP_DIRS = {".git", "packages", "node_modules"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(node, name):
    return [child for child in list(node) if local(child.tag) == name]


def first_text(node, name, default=""):
    found = children(node, name)
    return "".join(found[0].itertext()).strip() if found else default


def norm(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def initial_properties(project: Path):
    project_dir = str(project.parent.resolve()) + "/"
    root = ROOT.resolve()
    return {
        "Configuration": CONFIG,
        "Platform": PLATFORM,
        "ProjectDir": project_dir,
        "MSBuildProjectDirectory": str(project.parent.resolve()),
        "MSBuildThisFileDirectory": project_dir,
        "ProjectPath": str(project.resolve()),
        "ProjectName": project.stem,
        "SolutionDir": str(root) + "/",
        "SolutionPath": str(root / "Client_2012.sln"),
        "SolutionName": "Client_2012",
    }


def expand(value: str, props: dict, max_rounds=8):
    current = value or ""
    for _ in range(max_rounds):
        updated = re.sub(
            r"\$\(([^)]+)\)",
            lambda m: str(props.get(m.group(1), m.group(0))),
            current,
            flags=re.I,
        )
        if updated == current:
            break
        current = updated
    return current


def split_boolean(expr: str, operator: str):
    # Conditions in these legacy projects use simple quoted comparisons.
    # Split only outside quoted strings and parentheses.
    parts, start, quote, depth, i = [], 0, None, 0, 0
    upper = expr.upper()
    needle = f" {operator.upper()} "
    while i < len(expr):
        ch = expr[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'""":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and upper.startswith(needle, i):
            parts.append(expr[start:i].strip())
            i += len(needle)
            start = i
            continue
        i += 1
    if parts:
        parts.append(expr[start:].strip())
        return parts
    return None


def condition_result(condition: str, props: dict, base_dir: Path):
    if not condition or not condition.strip():
        return True
    expr = expand(condition.strip(), props)
    parts = split_boolean(expr, "Or")
    if parts:
        values = [condition_result(p, props, base_dir) for p in parts]
        return True if True in values else (None if None in values else False)
    parts = split_boolean(expr, "And")
    if parts:
        values = [condition_result(p, props, base_dir) for p in parts]
        return False if False in values else (None if None in values else True)

    exists = re.fullmatch(r"\s*Exists\(\s*(['""])(.*?)\1\s*\)\s*", expr, re.I)
    if exists:
        target = Path(exists.group(2))
        if not target.is_absolute():
            target = base_dir / target
        return target.exists()

    comparison = re.fullmatch(r"\s*(['""])(.*?)\1\s*(==|!=)\s*(['""])(.*?)\4\s*", expr)
    if comparison:
        left, op, right = comparison.group(2), comparison.group(3), comparison.group(5)
        equal = left.strip().lower() == right.strip().lower()
        return equal if op == "==" else not equal

    # Handle the common unquoted literal form without pretending to understand
    # arbitrary MSBuild functions or property functions.
    if "$(" not in expr and not re.search(r"[<>()]", expr):
        return expr.strip().lower() in {"true", "1"}
    return None


def combined_condition(parent, child, props, base_dir):
    a = condition_result(parent, props, base_dir)
    b = condition_result(child, props, base_dir)
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def evaluate_properties(project: Path, tree):
    props = initial_properties(project)
    root = tree.getroot()
    for group in children(root, "PropertyGroup"):
        result = condition_result(group.attrib.get("Condition", ""), props, project.parent)
        if result is not True:
            continue
        for item in list(group):
            name = local(item.tag)
            raw = "".join(item.itertext()).strip()
            props[name] = expand(raw, props)
    return props


def resolve_repo_path(project: Path, raw: str, props: dict):
    expanded = expand(raw, props).replace("\\", "/").strip()
    if "$(" in expanded:
        return None, "unresolved_property", expanded
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = project.parent / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None, "outside_repository", expanded
    if candidate.exists():
        return candidate, "resolved", expanded
    # Case-insensitive fallback mirrors the Windows runner on a Linux dev host.
    current = ROOT.resolve()
    try:
        relative = candidate.relative_to(current)
    except ValueError:
        return None, "outside_repository", expanded
    for part in relative.parts:
        if not current.is_dir():
            return None, "missing_path_component", expanded
        matches = [p for p in current.iterdir() if p.name.lower() == part.lower()]
        if len(matches) != 1:
            return None, "missing_or_ambiguous_path_component", expanded
        current = matches[0]
    return (current, "resolved", expanded) if current.exists() else (None, "missing_file", expanded)


def item_groups(root):
    for group in children(root, "ItemGroup"):
        yield group


def project_inventory(project: Path):
    try:
        tree = ET.parse(project)
    except (ET.ParseError, OSError) as error:
        return None, {"path": norm(project), "xml_error": str(error)}
    root = tree.getroot()
    props = evaluate_properties(project, tree)
    record = {
        "path": norm(project),
        "platform_toolset": props.get("PlatformToolset"),
        "configuration_type": props.get("ConfigurationType"),
        "imports": [],
        "project_references": [],
        "compile_items": [],
        "listed_headers": [],
        "active_build_settings": [],
        "unresolved_conditions": [],
    }

    for node in root.iter():
        tag = local(node.tag)
        if tag == "Import":
            raw = node.attrib.get("Project", "")
            condition = node.attrib.get("Condition", "")
            state = condition_result(condition, props, project.parent)
            resolved, status, expanded = resolve_repo_path(project, raw, props) if state is True else (None, "inactive" if state is False else "condition_unknown", expand(raw, props))
            record["imports"].append({
                "project": raw, "expanded": expanded, "condition": condition,
                "condition_state": state, "resolution": status,
                "resolved_path": norm(resolved) if resolved else None,
            })

    # Track inherited ItemGroup and item-level conditions for the requested config.
    for group in item_groups(root):
        group_state = condition_result(group.attrib.get("Condition", ""), props, project.parent)
        for item in list(group):
            tag = local(item.tag)
            state = combined_condition(group.attrib.get("Condition", ""),
                                       item.attrib.get("Condition", ""), props, project.parent)
            if tag == "ProjectReference":
                raw = item.attrib.get("Include", "")
                if state is True:
                    resolved, status, expanded = resolve_repo_path(project, raw, props)
                else:
                    resolved, status, expanded = None, ("inactive" if state is False else "condition_unknown"), expand(raw, props)
                record["project_references"].append({
                    "include": raw, "expanded": expanded,
                    "group_condition": group.attrib.get("Condition", ""),
                    "item_condition": item.attrib.get("Condition", ""),
                    "condition_state": state, "resolution": status,
                    "resolved_path": norm(resolved) if resolved else None,
                })
            elif tag == "ClCompile":
                raw = item.attrib.get("Include", "")
                if state is True:
                    resolved, status, expanded = resolve_repo_path(project, raw, props)
                    excluded = False
                    for meta in children(item, "ExcludedFromBuild"):
                        meta_state = condition_result(meta.attrib.get("Condition", ""), props, project.parent)
                        value = "".join(meta.itertext()).strip().lower()
                        if meta_state is True and value == "true":
                            excluded = True
                    if resolved and not excluded and resolved.suffix.lower() in SOURCE_EXTS:
                        record["compile_items"].append({"include": raw, "path": norm(resolved)})
                    elif not resolved:
                        record["compile_items"].append({"include": raw, "expanded": expanded, "resolution": status})
                elif state is None:
                    record["unresolved_conditions"].append({"item": "ClCompile", "include": raw,
                                                             "condition": item.attrib.get("Condition", "")})
            elif tag in ("ClInclude", "None"):
                raw = item.attrib.get("Include", "")
                if state is True:
                    resolved, status, expanded = resolve_repo_path(project, raw, props)
                    if resolved and resolved.suffix.lower() in HEADER_EXTS:
                        record["listed_headers"].append(norm(resolved))

    for group in children(root, "ItemDefinitionGroup"):
        state = condition_result(group.attrib.get("Condition", ""), props, project.parent)
        if state is not True:
            if state is None:
                record["unresolved_conditions"].append({"item": "ItemDefinitionGroup",
                                                         "condition": group.attrib.get("Condition", "")})
            continue
        settings = {"condition": group.attrib.get("Condition", ""),
                    "include_directories": [], "library_directories": [],
                    "additional_dependencies": [], "preprocessor_definitions": []}
        for definition in list(group):
            kind = local(definition.tag)
            if kind not in ("ClCompile", "Link"):
                continue
            for field in list(definition):
                name = local(field.tag)
                if name not in ("AdditionalIncludeDirectories", "AdditionalLibraryDirectories",
                                "AdditionalDependencies", "PreprocessorDefinitions"):
                    continue
                raw = "".join(field.itertext()).strip()
                expanded = expand(raw, props)
                values = [x.strip() for x in expanded.split(";") if x.strip() and not x.strip().startswith("%(")]
                target = {
                    "AdditionalIncludeDirectories": "include_directories",
                    "AdditionalLibraryDirectories": "library_directories",
                    "AdditionalDependencies": "additional_dependencies",
                    "PreprocessorDefinitions": "preprocessor_definitions",
                }[name]
                settings[target].extend(values)
        record["active_build_settings"].append(settings)

    return props, record


def project_graph(start: Path):
    queue, seen, records, source_files, listed_headers = [start], set(), [], set(), set()
    dependency_paths = []
    while queue:
        project = queue.pop(0).resolve()
        if project in seen:
            continue
        seen.add(project)
        evaluated = project_inventory(project)
        if evaluated[0] is None:
            records.append(evaluated[1])
            continue
        props, record = evaluated
        records.append(record)
        source_files.update(x["path"] for x in record["compile_items"] if "path" in x)
        listed_headers.update(record["listed_headers"])
        for ref in record["project_references"]:
            if ref["condition_state"] is not True:
                continue
            if ref["resolution"] == "resolved" and ref["resolved_path"]:
                child = (ROOT / ref["resolved_path"]).resolve()
                if child.suffix.lower() == ".vcxproj" and child not in seen:
                    queue.append(child)
            else:
                dependency_paths.append({"project": record["path"], **ref})
    return records, sorted(source_files), sorted(listed_headers), dependency_paths


def scan_selected_sources(source_files, listed_headers):
    patterns = {
        "tbb_includes": re.compile(r"#\s*include\s*[<""](?:tbb/[^>""]+|tbb\.h)[>""]", re.I),
        "telemetry_mentions": re.compile(r"Telemetry2SDK|TelemetryClient|Telemetry", re.I),
        "vmprotect_mentions": re.compile(r"VMProtectSDK\.h|VMProtect[A-Za-z0-9_]*\s*\(", re.I),
        "vmprotect_guards": re.compile(r"^\s*#\s*(?:if|ifdef|ifndef|elif).*(?:VMProtect|VMP)", re.I | re.M),
    }
    hits = {key: [] for key in patterns}
    selected = [(p, "compiled_translation_unit") for p in source_files]
    selected.extend((p, "project_listed_header_not_proven_included") for p in listed_headers)
    for relative, role in selected:
        path = ROOT / relative
        try:
            data = path.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        for key, pattern in patterns.items():
            for match in pattern.finditer(data):
                line = data.count("\n", 0, match.start()) + 1
                hits[key].append({"file": relative, "line": line,
                                  "file_role": role, "match": match.group(0).strip()[:180]})
    return hits


def dependency_metadata(projects):
    tokens = re.compile(r"TBB|Telemetry|VMProtect|DSBaseClasses|DirectShow", re.I)
    hits = []
    for project in projects:
        for setting_group in project.get("active_build_settings", []):
            for field in ("include_directories", "library_directories", "additional_dependencies"):
                for value in setting_group[field]:
                    if tokens.search(value):
                        hits.append({"project": project["path"], "configuration": CONFIG_KEY,
                                     "setting": field, "value": value})
    return hits


def main():
    start = ROOT / "WindowsClient/WindowsClient.vcxproj"
    projects, compiled_sources, listed_headers, unresolved_refs = project_graph(start)
    source_hits = scan_selected_sources(compiled_sources, listed_headers)
    result = {
        "audit_type": "static Debug|Win32 reachable-project and selected-source inventory; not a build",
        "configuration": CONFIG_KEY,
        "solution": "Client_2012.sln",
        "target_project": "WindowsClient/WindowsClient.vcxproj",
        "expected_output": "RobloxPlayerBetaRaw.exe",
        "project_count": len(projects),
        "compiled_translation_unit_count": len(compiled_sources),
        "project_listed_header_count": len(listed_headers),
        "project_inventory": projects,
        "selected_source_reference_scan": source_hits,
        "active_dependency_build_metadata": dependency_metadata(projects),
        "unresolved_active_project_references": unresolved_refs,
        "limitations": [
            "This is a conservative static evaluator, not MSBuild; imported .props/.targets are inventoried but not fully evaluated.",
            "Property functions, arbitrary MSBuild functions, environment-dependent properties, and all MSBuild condition syntax are not evaluated.",
            "Project references with unknown conditions or unresolved properties are reported and are not followed.",
            "Listed headers are scanned as candidates; the audit does not evaluate actual preprocessor include graphs or conditional compilation.",
            "A project-listed source file is considered selected unless an explicit active ExcludedFromBuild=true is present; imported build logic may alter this.",
            "No SDKs are downloaded, no protection features are disabled, and no compiler or linker is run.",
            "A successful audit does not mean RobloxPlayerBetaRaw.exe was built."
        ]
    }
    destination = ROOT / "windows-configuration-audit.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    counts = {key: len(value) for key, value in source_hits.items()}
    unresolved_condition_count = sum(len(p.get("unresolved_conditions", [])) for p in projects)
    print(json.dumps({
        "output": destination.name,
        "configuration": CONFIG_KEY,
        "projects": len(projects),
        "compiled_translation_units": len(compiled_sources),
        "listed_headers": len(listed_headers),
        "source_reference_counts": counts,
        "active_dependency_metadata_hits": len(result["active_dependency_build_metadata"]),
        "unresolved_active_project_references": len(unresolved_refs),
        "unresolved_conditions": unresolved_condition_count,
        "audit_type": result["audit_type"]
    }, indent=2))
    return 1 if any("xml_error" in p for p in projects) else 0


if __name__ == "__main__":
    sys.exit(main())
