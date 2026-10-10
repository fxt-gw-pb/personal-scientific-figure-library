"""Static website builder for the figure library.

The frontend in ``site/`` is plain HTML/CSS/ES modules and never changes per entry.
This module only generates ``data/library.json`` and the media it references, using
an explicit whitelist. Two modes share the same frontend:

* public: GitHub Pages. Only accepted collected entries that opted in through
  ``publication`` (plus clearly labelled examples when configured). No reference
  originals, raw data, imported code, reviewer names or validation internals.
* local: private management view of every entry, including drafts, reference views,
  comparisons and validation problems. Never deploy this output.

The CLI passes its own helpers in as ``core`` so that this module does not import
``figurelib`` a second time (exception classes must stay identical).
"""
from __future__ import annotations

import functools
import http.server
import json
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

SITE_API_VERSION = 1
MARKER = ".figurelib-site"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_SVG_BYTES = 12_000_000
SVG_ELEMENTS = {
    "svg", "g", "defs", "style", "path", "use", "clipPath", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "linearGradient", "radialGradient", "stop", "title",
    "desc", "mask", "pattern", "symbol", "image",
}
URL_REFERENCE = re.compile(r"url\(\s*['\"]?([^)'\"]*)", re.IGNORECASE)
DEFAULT_CONFIG = {
    "title": "科研图库",
    "subtitle": "",
    "repository": {"url": None, "branch": "main"},
    "include_examples": True,
    "link_repository_files": True,
    "features": {},
}
# Public text fields that an opted-in, reviewed entry may show. Everything else stays in Git.
CONTRACT_COLUMN_KEYS = ("name", "type", "required", "unit", "description")


def load_config(core, root: Path) -> dict:
    path = root / "site" / "site.config.json"
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_file():
        loaded = core.read_json(path)
        if not isinstance(loaded, dict):
            raise core.LibraryError("site/site.config.json 必须是 JSON 对象")
        for key, value in loaded.items():
            if key.startswith("$"):
                continue
            if key not in DEFAULT_CONFIG:
                raise core.LibraryError(f"site.config.json 含未知字段：{key}")
            if isinstance(DEFAULT_CONFIG[key], dict):
                if not isinstance(value, dict):
                    raise core.LibraryError(f"site.config.json 的 {key} 必须是对象")
                config[key].update(value)
            else:
                config[key] = value
    url = config["repository"].get("url")
    if url is not None and not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(url)):
        raise core.LibraryError("repository.url 应形如 https://github.com/OWNER/REPO，或设为 null")
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", str(config["repository"].get("branch") or "")):
        raise core.LibraryError("repository.branch 无效")
    for key in ("include_examples", "link_repository_files"):
        if not isinstance(config[key], bool):
            raise core.LibraryError(f"site.config.json 的 {key} 必须是 true/false")
    if not all(isinstance(k, str) and isinstance(v, bool) for k, v in config["features"].items()):
        raise core.LibraryError("site.config.json 的 features 只能是 名称: true/false")
    return config


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_urls(text: str) -> bool:
    return all(target.strip().startswith("#") for target in URL_REFERENCE.findall(text))


def sanitize_svg(core, source: Path, target: Path):
    """Keep drawing primitives only: no scripts, events, external references or metadata."""
    data = source.read_bytes()
    if len(data) > MAX_SVG_BYTES:
        raise core.LibraryError(f"SVG 超过 {MAX_SVG_BYTES // 1_000_000} MB，不适合直接放进网页：{source.name}")
    if b"<!ENTITY" in data:
        raise core.LibraryError(f"SVG 含 XML 实体声明，拒绝发布：{source.name}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise core.LibraryError(f"SVG 无法解析：{source.name}：{exc}") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise core.LibraryError(f"不是 SVG 根节点：{source.name}")

    def clean(element):
        tag = _local(element.tag)
        for name in list(element.attrib):
            value = element.attrib[name]
            lowered = _local(name).lower()
            if lowered.startswith("on") or "javascript:" in value.lower() or not _safe_urls(value):
                del element.attrib[name]
            elif lowered == "href" and not (value.startswith("#") or (tag == "image" and value.startswith("data:image/png;base64,"))):
                del element.attrib[name]
        for child in list(element):
            child_tag = child.tag if isinstance(child.tag, str) else ""
            keep = child_tag.startswith(f"{{{SVG_NS}}}") and _local(child_tag) in SVG_ELEMENTS
            if keep and _local(child_tag) == "style":
                text = child.text or ""
                keep = "@import" not in text.lower() and _safe_urls(text)
            if keep:
                clean(child)
            else:
                element.remove(child)

    clean(root)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    text = ET.tostring(root, encoding="unicode")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + text + "\n", encoding="utf-8")


def _string_list(values) -> list[str]:
    result = []
    for value in values or []:
        result.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True))
    return result


def _read_optional_yaml(core, entry: Path, relative):
    if not relative:
        return None
    path = core.internal(entry, relative)
    if not path.is_file():
        return None
    try:
        return core.read_yaml(path)
    except core.LibraryError:
        return None


def _repository_links(config, prefix: str, meta, entry: Path, *, public: bool):
    url = config["repository"]["url"]
    if not url or not config["link_repository_files"]:
        return {"entry": None, "files": []}
    branch = config["repository"]["branch"]
    files = [("元数据", "figure.yaml"), ("说明", "README.md"), ("样式", meta["implementation"]["style"]), ("绘图代码", meta["implementation"]["entrypoint"]), ("依赖", meta["implementation"]["requirements"]), ("数据契约", meta["data"]["contract"]), ("矢量 SVG", meta["assets"]["vector"]), ("PDF", "outputs/figure.pdf")]
    if not public or meta["kind"] == "example":
        # Raw inputs and review records are linked only for demos or the private local view.
        files += [("示例数据", meta["data"]["path"]), ("验收记录", "review.yaml")]
    if not public:
        files += [("参考图", meta["assets"]["reference"])]
    result, seen = [], set()
    for label, relative in files:
        if not relative or relative in seen or not core_exists(entry, relative):
            continue
        seen.add(relative)
        result.append({"label": label, "path": f"{prefix}/{relative}", "url": f"{url}/blob/{branch}/{prefix}/{relative}"})
    return {"entry": f"{url}/tree/{branch}/{prefix}", "files": result}


def core_exists(entry: Path, relative: str) -> bool:
    candidate = entry.joinpath(*relative.split("/"))
    try:
        candidate.resolve().relative_to(entry.resolve())
    except (ValueError, RuntimeError):
        return False
    return candidate.is_file() and not candidate.is_symlink()


def _contract_summary(contract):
    if not isinstance(contract, dict) or not isinstance(contract.get("columns"), list):
        return None
    columns = []
    for column in contract["columns"]:
        if isinstance(column, dict):
            columns.append({key: column.get(key) for key in CONTRACT_COLUMN_KEYS if key in column})
    return {"description": str(contract.get("description") or ""), "columns": columns, "constraints": _string_list(contract.get("constraints"))}


def _review_summary(review, *, local: bool):
    if not isinstance(review, dict):
        return None
    checks = []
    for check in review.get("checks") or []:
        if isinstance(check, str):
            checks.append({"kind": "note", "summary": check})
        elif isinstance(check, dict) and isinstance(check.get("summary"), str):
            checks.append({"kind": str(check.get("kind") or "note"), "summary": check["summary"]})
    result = {"summary": str(review.get("summary") or ""), "known_differences": _string_list(review.get("known_differences")), "checks": checks}
    if local:
        result["provenance"] = [p for p in review.get("provenance") or [] if isinstance(p, dict)]
        result["reviewer"] = review.get("reviewer")
        result["flags"] = {key: bool(review.get(key)) for key in ("visual_checked", "data_checked", "reuse_checked")}
    return result


def _media(core, entry: Path, meta, staging: Path, *, local: bool):
    identifier = meta["id"]
    media = {"thumbnail": None, "preview": None, "vector": None, "reference": None, "comparison": None, "thumbnail_is_reference": False}

    def present(relative):
        return relative and core_exists(entry, relative)

    for field, name in (("preview", "preview.png"), ("thumbnail", "thumb.png")):
        relative = meta["assets"][field]
        if present(relative):
            # Re-encode from pixels: drops text chunks, EXIF and other embedded metadata.
            core.safe_png(core.internal(entry, relative, required=True), staging / "media" / identifier / name)
            media[field] = f"media/{identifier}/{name}"
    if present(meta["assets"]["vector"]):
        sanitize_svg(core, core.internal(entry, meta["assets"]["vector"], required=True), staging / "media" / identifier / "figure.svg")
        media["vector"] = f"media/{identifier}/figure.svg"
    if local:
        for field, stem in (("reference", "reference"), ("comparison", "comparison")):
            relative = meta["assets"][field]
            if present(relative):
                # Reference views may be JPEG/WebP; keep pixels only, as PNG.
                image = core.read_raster(core.internal(entry, relative, required=True))
                destination = staging / "media" / identifier / f"{stem}.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                core.Image.frombytes("RGBA", image.size, image.tobytes()).save(destination, format="PNG")
                media[field] = f"media/{identifier}/{stem}.png"
        if media["thumbnail"] is None and media["reference"]:
            image = core.read_raster(staging / media["reference"])
            image.thumbnail((640, 480))
            image.save(staging / "media" / identifier / "thumb.png", format="PNG")
            media["thumbnail"] = f"media/{identifier}/thumb.png"
            media["thumbnail_is_reference"] = True
    return media


def entry_record(core, root: Path, entry: Path, meta, staging: Path, config, *, local: bool, validation=None):
    prefix = entry.relative_to(root).as_posix()
    style = _read_optional_yaml(core, entry, meta["implementation"]["style"])
    contract = _read_optional_yaml(core, entry, meta["data"]["contract"])
    review = _read_optional_yaml(core, entry, "review.yaml")
    public = not local
    record = {
        "id": meta["id"], "title": meta["title"], "kind": meta["kind"], "status": meta["status"],
        "family": meta["family"], "tags": list(meta["tags"]), "created": str(meta["created"]), "why_saved": meta["why_saved"],
        "data": {"kind": meta["data"]["kind"], "notes": meta["data"]["notes"]},
        "source": {key: meta["source"][key] for key in ("kind", "citation", "doi", "url", "figure_label")},
        "reuse": {"scope": list(meta["reuse"]["scope"]), "caveats": list(meta["reuse"]["caveats"])},
        "implementation": {"language": meta["implementation"]["language"]},
        "style": style if isinstance(style, dict) else None,
        "contract": _contract_summary(contract),
        "review": _review_summary(review, local=local) if (local or meta["status"] in core.STATES_ACCEPTED) else None,
        "media": _media(core, entry, meta, staging, local=local),
        "path": prefix,
        "links": _repository_links(config, prefix, meta, entry, public=public),
        "validation": validation,
    }
    if public and meta["kind"] == "collected":
        record["publication"] = {"rights_note": meta["publication"]["rights_note"]}
    return record


def _public_selection(core, root: Path, config, include_examples: bool):
    selected = []
    for entry in core.entries(root, include_examples):
        meta = core.metadata(root, entry)
        if meta["kind"] == "collected":
            if not meta["publication"]["include_in_public_catalog"]:
                continue
            if meta["status"] not in core.STATES_ACCEPTED:
                raise core.LibraryError(f"{meta['id']} 已勾选公开，但尚未经过 reproduced/reusable 审核")
            if not core.meaningful(meta["publication"]["rights_note"], 8):
                raise core.LibraryError(f"{meta['id']} 缺少明确的 publication.rights_note")
        selected.append((entry, core.require_valid(root, entry)))
    return selected


def _default_target(root: Path, local: bool) -> Path:
    return root / ("workspace/site-local" if local else "_site")


def _prepare_target(core, root: Path, value) -> Path:
    target = (Path(value).expanduser() if value else None)
    target = target.resolve() if target else None
    for folder in ("figures", "examples", "templates", "schema", "scripts", "site", "catalog", "docs", "prompts", "tests", ".github"):
        protected = (root / folder).resolve()
        if target == root.resolve() or target.is_relative_to(protected):
            raise core.LibraryError("网页输出不能写入仓库根目录或源码/条目目录")
    if target.is_symlink():
        raise core.LibraryError("网页输出目录不能是符号链接")
    if target.exists() and not (target / MARKER).is_file():
        raise core.LibraryError(f"输出目录已存在且不是此前生成的网页：{target}；请换一个目录")
    return target


def build_site(core, root: Path, *, out=None, local=False, include_examples=None):
    config = load_config(core, root)
    frontend = root / "site"
    if not (frontend / "index.html").is_file():
        raise core.LibraryError("缺少前端源码 site/index.html")
    include_examples = config["include_examples"] if include_examples is None else include_examples
    target = _prepare_target(core, root, out or _default_target(root, local))
    records, problems = [], []
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.site-", dir=target.parent))
    try:
        shutil.copytree(frontend, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns("site.config.json", ".DS_Store", "*.tmp"))
        if local:
            for entry in core.entries(root, include_examples):
                meta, errors, notes = core.validate_entry(root, entry)
                if meta is None:
                    problems.append({"path": entry.relative_to(root).as_posix(), "errors": errors})
                    continue
                validation = {"ok": not errors, "errors": errors, "notes": notes}
                records.append(entry_record(core, root, entry, meta, staging, config, local=True, validation=validation))
        else:
            for entry, meta in _public_selection(core, root, config, include_examples):
                records.append(entry_record(core, root, entry, meta, staging, config, local=False))
        version_file = root / "VERSION"
        library = {
            "api_version": SITE_API_VERSION,
            "mode": "local" if local else "public",
            "generator": "figurelib " + (version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "unknown"),
            "site": {key: config[key] for key in ("title", "subtitle", "repository", "features")},
            "entries": records,
            "problems": problems,
        }
        core.check_schema(root, "site-data", library)
        core.write_text(staging / "data" / "library.json", core.json_text(library))
        (staging / ".nojekyll").write_text("", encoding="utf-8")
        (staging / MARKER).write_text("Generated by `python scripts/figurelib.py site`. Safe to delete and rebuild.\n", encoding="utf-8")
        core.commit_directory(staging, target, replace=target.exists())
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target, records, problems


def serve(target: Path, port: int):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(target))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"本地预览：http://127.0.0.1:{server.server_address[1]}/  （Ctrl+C 结束）", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
