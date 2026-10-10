#!/usr/bin/env python3
"""A small, explicit scientific figure repository CLI. No network, install or search agent."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import html
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import uuid
from datetime import date, datetime, timezone
from functools import lru_cache

try:
    import yaml
    import jsonschema
    from PIL import Image, ImageDraw, ImageOps
except ImportError as exc:
    raise SystemExit(f"缺少依赖：{exc.name}。请自行运行 python -m pip install -r requirements.txt")

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SHA_PATTERN = re.compile(r"^[a-f0-9]{64}$")
STATES_ACCEPTED = {"reproduced", "reusable"}
IGNORED_DIRS = {"__pycache__", ".git", ".pytest_cache", ".ipynb_checkpoints", ".venv", "venv"}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
CANONICAL_ASSETS = {"preview": "outputs/figure.png", "thumbnail": "outputs/thumb.png", "vector": "outputs/figure.svg"}
MAX_IMAGE_PIXELS = 60_000_000
LEFTOVER_PREFIXES = (".outputs.render-", ".outputs.backup-", ".render-")


class LibraryError(Exception):
    """A user-actionable error, without a Python traceback."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            raise LibraryError("YAML 键必须是简单的文字或数字")
        if duplicate:
            raise LibraryError(f"YAML 出现重复键：{key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def read_yaml(path: Path):
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise LibraryError(f"无法读取 {path.name}：{exc}") from exc


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LibraryError(f"无法读取 {path.name}：{exc}") from exc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def object_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_text(path: Path, text: str):
    """Write only if changed, and replace atomically on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_yaml(path: Path, value):
    write_text(path, yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=110))


def valid_id(value: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise LibraryError("ID 应为 3–64 位小写字母、数字或连字符，且以字母或数字开头")
    return value


def internal(entry: Path, value, *, required=False) -> Path:
    """Reject absolute paths, traversal and resolved escapes, including Windows syntax."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise LibraryError(f"条目内路径应为非空的相对路径：{value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or PureWindowsPath(value).drive or any(p in {"..", "."} for p in value.split("/")):
        raise LibraryError(f"拒绝不安全的条目路径：{value!r}")
    if any(not p for p in value.split("/")):
        raise LibraryError(f"路径包含空片段：{value!r}")
    target = entry.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(entry.resolve())
    except (ValueError, RuntimeError):
        raise LibraryError(f"路径或符号链接越过条目目录：{value!r}")
    if required and not target.is_file():
        raise LibraryError(f"缺少文件：{value}")
    if target.exists() and not target.is_file():
        raise LibraryError(f"声明的文件路径实际不是文件：{value}")
    return target


def resolve_entry(root: Path, identifier: str) -> Path:
    identifier = valid_id(identifier)
    for collection in ("figures", "examples"):
        candidate = root / collection / identifier
        if candidate.exists() or candidate.is_symlink():
            try:
                candidate.resolve().relative_to((root / collection).resolve())
            except (ValueError, RuntimeError):
                raise LibraryError(f"条目目录符号链接越界：{collection}/{identifier}")
            if candidate.is_symlink() or not candidate.is_dir():
                raise LibraryError(f"条目目录必须是普通目录：{collection}/{identifier}")
            return candidate
    raise LibraryError(f"找不到 ID：{identifier}。已直接检查 figures/{identifier} 与 examples/{identifier}")


def entries(root: Path, include_examples=False) -> list[Path]:
    result = []
    for collection in ["figures"] + (["examples"] if include_examples else []):
        folder = root / collection
        if not folder.exists():
            continue
        for child in sorted(folder.iterdir(), key=lambda x: x.name):
            if child.name.startswith(".") or not child.is_dir():
                continue
            if not (child / "figure.yaml").is_file():
                raise LibraryError(f"{collection}/{child.name} 缺少 figure.yaml；请移到工作目录或补齐条目")
            valid_id(child.name)
            if child.is_symlink():
                raise LibraryError(f"条目目录不接受符号链接：{collection}/{child.name}")
            result.append(child)
    ids = [p.name for p in result]
    if len(ids) != len(set(ids)):
        raise LibraryError("figures 与 examples 存在重复 ID，请为真实收藏使用独立 ID")
    return result


@lru_cache(maxsize=24)
def schema_validator(root_string: str, name: str):
    path = Path(root_string) / "schema" / f"{name}.schema.json"
    schema = read_json(path)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def check_schema(root: Path, name: str, value):
    problems = sorted(schema_validator(str(root.resolve()), name).iter_errors(value), key=lambda e: str(list(e.path)))
    if problems:
        details = "; ".join(f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in problems[:6])
        raise LibraryError(f"{name} 格式不合格：{details}")


def metadata(root: Path, entry: Path):
    meta = read_yaml(internal(entry, "figure.yaml", required=True))
    check_schema(root, "figure", meta)
    if meta["id"] != entry.name:
        raise LibraryError(f"figure.yaml 的 ID {meta['id']} 与目录名 {entry.name} 不一致")
    expected_kind = "example" if entry.parent.name == "examples" else "collected"
    if meta["kind"] != expected_kind:
        raise LibraryError(f"{entry.parent.name}/{entry.name} 的 kind 应为 {expected_kind}")
    return meta


def metadata_paths(meta):
    for item in meta["source"]["files"]:
        yield "source.files", item["path"]
    for section, keys in (("data", ("path", "contract")), ("implementation", ("entrypoint", "requirements", "style")), ("assets", ("reference", "preview", "thumbnail", "vector", "comparison"))):
        for key in keys:
            value = meta[section][key]
            if value is not None:
                yield f"{section}.{key}", value


def safe_files(folder: Path, entry: Path) -> list[Path]:
    """Only source/support files; caches and symlink directory dependencies are excluded."""
    if not folder.exists():
        return []
    collected = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        current = Path(dirpath)
        keep = []
        for name in sorted(dirnames):
            if name in IGNORED_DIRS or name.startswith(".render-"):
                continue
            child = current / name
            if child.is_symlink():
                raise LibraryError(f"为保证可携带性，代码/数据目录不能含符号链接：{child.relative_to(entry)}")
            keep.append(name)
        dirnames[:] = keep
        for name in sorted(filenames):
            if name in IGNORED_FILES or name.endswith((".pyc", ".pyo", ".tmp")):
                continue
            child = current / name
            relative = child.relative_to(entry).as_posix()
            internal(entry, relative, required=True)
            if child.is_symlink():
                raise LibraryError(f"为保证可携带性，代码/数据文件不能是符号链接：{relative}")
            collected.append(child)
    return sorted(collected)


def source_check(entry: Path, meta):
    seen = set()
    for item in meta["source"]["files"]:
        if item["path"] in seen:
            raise LibraryError(f"source.files 路径重复：{item['path']}")
        seen.add(item["path"])
        path = internal(entry, item["path"], required=True)
        if sha256(path) != item["sha256"]:
            raise LibraryError(f"原始材料 SHA-256 已改变：{item['path']}。请保留原件、追加修订材料并说明变化")
    reference = meta["assets"]["reference"]
    if reference is not None:
        if reference not in seen:
            raise LibraryError("assets.reference 必须同时列入 source.files 并保存 SHA-256")
        read_raster(internal(entry, reference, required=True))


def read_raster(path: Path, *, png_only=False) -> Image.Image:
    try:
        with Image.open(path) as image:
            if png_only and image.format != "PNG":
                raise LibraryError(f"不是实际 PNG 图像：{path.name}")
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise LibraryError(f"图像尺寸无效或超过 {MAX_IMAGE_PIXELS:,} 像素：{path.name}")
            image.load()
            return ImageOps.exif_transpose(image).convert("RGBA")
    except LibraryError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise LibraryError(f"无法解码图像 {path.name}：{exc}") from exc


def validate_csv(path: Path, contract, *, accepted=False) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            if not fields or any(not f or not f.strip() for f in fields) or len(fields) != len(set(fields)):
                raise LibraryError(f"CSV 表头为空、缺失或重复：{path.name}")
            if contract:
                columns = contract["columns"]
                if len({c["name"] for c in columns}) != len(columns):
                    raise LibraryError("data/contract.yaml 的列名重复")
                missing = [c["name"] for c in columns if c["required"] and c["name"] not in fields]
                if missing:
                    raise LibraryError(f"CSV 缺少契约要求的列：{', '.join(missing)}")
            rows = 0
            for row in reader:
                rows += 1
                if None in row or any(value is None for value in row.values()):
                    raise LibraryError(f"CSV 第 {rows + 1} 行列数与表头不一致")
            if not rows:
                if accepted:
                    raise LibraryError("验收状态的 CSV 只有表头，没有数据行")
                return ["CSV 目前只有表头；条目仍为脚手架"]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise LibraryError(f"无法读取 CSV {path.name}：{exc}") from exc
    return []


def input_snapshot(entry: Path, meta, data_override: Path | None = None, style_override: Path | None = None):
    data_relative = meta["data"]["path"]
    style_relative = meta["implementation"]["style"]
    if data_relative is None or style_relative is None:
        raise LibraryError("运行需要 data.path 和 implementation.style")
    paths = {}
    for folder_name, role in (("code", "implementation"), ("data", "data-support")):
        for path in safe_files(entry / folder_name, entry):
            relative = path.relative_to(entry).as_posix()
            if relative not in (data_relative, style_relative):
                paths[relative] = (role, path)
    for section, key, role in (("implementation", "entrypoint", "entrypoint"), ("implementation", "requirements", "requirements"), ("data", "contract", "contract")):
        relative = meta[section][key]
        if relative is not None:
            paths[relative] = (role, internal(entry, relative, required=True))
    for item in meta["source"]["files"]:
        role = "reference" if item["path"] == meta["assets"]["reference"] else "source-material"
        paths[item["path"]] = (role, internal(entry, item["path"], required=True))
    data_path = data_override or internal(entry, data_relative, required=True)
    style_path = style_override or internal(entry, style_relative, required=True)
    data_key = f"external/{data_path.name}" if data_override else data_relative
    style_key = f"external/{style_path.name}" if style_override else style_relative
    # Roles disambiguate an external data and style file that happen to share a basename.
    result = [{"path": p, "role": role, "sha256": sha256(path)} for p, (role, path) in sorted(paths.items())]
    result += [{"path": data_key, "role": "data", "sha256": sha256(data_path)}, {"path": style_key, "role": "style", "sha256": sha256(style_path)}]
    return sorted(result, key=lambda item: (item["role"], item["path"]))


def metadata_basis(meta):
    """Only the provenance, data meaning and execution choices to which review applies."""
    return {"source": meta["source"], "data": meta["data"], "implementation": meta["implementation"], "reference": meta["assets"]["reference"]}


def recipe_digest(inputs, basis) -> str:
    # A changed-input check changes only the main CSV, not code, contract or dependencies.
    recipe = [{**item, "path": "<style>" if item["role"] == "style" else item["path"]} for item in inputs if item["role"] != "data"]
    return object_sha256({"files": recipe, "metadata_basis": basis})


def data_digest(inputs) -> str:
    records = [item for item in inputs if item["role"] == "data"]
    if len(records) != 1:
        raise LibraryError("run.json 应恰好记录一个主数据输入")
    return records[0]["sha256"]


def inspect_run(run, identifier: str):
    if not isinstance(run, dict) or run.get("schema_version") != 1 or run.get("entry_id") != identifier or run.get("success") is not True:
        raise LibraryError("run.json 的版本、条目 ID 或成功状态不正确")
    inputs = run.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise LibraryError("run.json 缺少输入指纹")
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {"path", "role", "sha256"}:
            raise LibraryError("run.json 输入记录结构无效")
        if not isinstance(item["path"], str) or not isinstance(item["role"], str) or not isinstance(item["sha256"], str) or not SHA_PATTERN.fullmatch(item["sha256"]):
            raise LibraryError("run.json 的输入路径/角色/SHA-256 无效")
        # No absolute or traversing paths may be retained in portable evidence.
        p = PurePosixPath(item["path"])
        if p.is_absolute() or PureWindowsPath(item["path"]).drive or ".." in p.parts or "\\" in item["path"]:
            raise LibraryError("run.json 包含不可携带的输入路径")
    if len({(i["role"], i["path"]) for i in inputs}) != len(inputs):
        raise LibraryError("run.json 输入指纹存在重复项")
    basis = run.get("metadata_basis")
    if not isinstance(basis, dict) or run.get("basis_sha256") != object_sha256(basis):
        raise LibraryError("run.json 缺少自洽的执行与数据来源语义摘要")
    if run.get("input_sha256") != object_sha256(inputs) or run.get("recipe_sha256") != recipe_digest(inputs, basis) or run.get("data_sha256") != data_digest(inputs):
        raise LibraryError("run.json 的输入摘要不自洽")
    outputs = run.get("outputs")
    if not isinstance(outputs, dict) or not {"figure.png", "figure.svg", "thumb.png"}.issubset(outputs):
        raise LibraryError("run.json 缺少必需产物摘要")
    for name, digest in outputs.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not SHA_PATTERN.fullmatch(digest):
            raise LibraryError("run.json 的产物指纹无效")
        p = PurePosixPath(name)
        if p.is_absolute() or PureWindowsPath(name).drive or ".." in p.parts or "\\" in name:
            raise LibraryError("run.json 包含不安全的产物路径")
    if not isinstance(run.get("argv"), list) or not run["argv"] or not all(isinstance(x, str) for x in run["argv"]):
        raise LibraryError("run.json 缺少可核对的运行参数")
    return run


def verify_current_run(entry: Path, meta):
    run_path = internal(entry, "outputs/run.json", required=True)
    run = inspect_run(read_json(run_path), meta["id"])
    if run.get("output_mode") != "canonical":
        raise LibraryError("主 outputs/run.json 不是主运行记录")
    if run["metadata_basis"] != metadata_basis(meta):
        raise LibraryError("运行证据过期：来源、数据语义、参考图或执行入口已改变，请重新 render 并审核")
    expected_argv = ["python" if meta["implementation"]["language"] == "python" else "Rscript", meta["implementation"]["entrypoint"], "--data", meta["data"]["path"], "--style", meta["implementation"]["style"], "--out", "outputs"]
    if run["argv"] != expected_argv:
        raise LibraryError("主运行记录的入口/引擎/参数与 figure.yaml 不一致")
    actual = input_snapshot(entry, meta)
    if run["inputs"] != actual:
        old = {(i["role"], i["path"]): i["sha256"] for i in run["inputs"]}
        new = {(i["role"], i["path"]): i["sha256"] for i in actual}
        changes = [key[1] for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]
        raise LibraryError(f"运行证据过期：输入已改变（{', '.join(changes[:8])}），请重新 render 并审核")
    for relative, expected in run["outputs"].items():
        output = internal(entry, f"outputs/{relative}", required=True)
        if sha256(output) != expected:
            raise LibraryError(f"运行产物已改变：outputs/{relative}；请重新 render 并审核")
    return run


def meaningful(value, minimum=8) -> bool:
    return isinstance(value, str) and len(re.sub(r"\s", "", value)) >= minimum


def check_review(entry: Path, meta, review, run):
    if review["reviewed_run"] != sha256(entry / "outputs" / "run.json"):
        raise LibraryError("审核未绑定当前 run.json；重新运行后必须重新检查并填写 reviewed_run")
    if not review["visual_checked"] or not review["data_checked"]:
        raise LibraryError("reproduced/reusable 必须分别完成 visual_checked 和 data_checked")
    if not meaningful(review["summary"]):
        raise LibraryError("审核 summary 需写出具体检查结论，不能只写 OK")
    if not meaningful(review["reviewer"], 2):
        raise LibraryError("审核需填写 reviewer，说明由谁检查")
    if not any(meaningful(c, 6) if isinstance(c, str) else meaningful(c.get("summary"), 6) for c in review["checks"]):
        raise LibraryError("审核 checks 需至少一条具体的检查记录")
    if meta["status"] != "reusable":
        return
    if not review["reuse_checked"]:
        raise LibraryError("reusable 还需要 reuse_checked")
    candidates = [c for c in review["checks"] if isinstance(c, dict) and c.get("kind") == "changed-input"]
    if not candidates:
        raise LibraryError("reusable 需 changed-input 检查，指向实际换数据运行的证据")
    failures = []
    for check in candidates:
        try:
            if not meaningful(check.get("summary")):
                raise LibraryError("changed-input 的 summary 必须说明改变了什么、检查到什么")
            evidence_path = internal(entry, check.get("run"), required=True)
            evidence = inspect_run(read_json(evidence_path), meta["id"])
            if evidence.get("output_mode") != "variant":
                raise LibraryError("换数据证据必须来自带 --out 的变体运行")
            if evidence["data_sha256"] == run["data_sha256"]:
                raise LibraryError("换数据证据的 CSV 内容与主运行相同；仅改文件名或样式不算换数据")
            if evidence["recipe_sha256"] != run["recipe_sha256"]:
                raise LibraryError("换数据证据的代码、依赖、契约或样式与当前主运行不一致")
            return
        except LibraryError as exc:
            failures.append(str(exc))
    raise LibraryError("没有有效的换数据证据：" + "; ".join(failures))


def validate_entry(root: Path, entry: Path):
    """Return (metadata or None, errors, pending notes). Never change entry contents."""
    errors, notes = [], []
    try:
        meta = metadata(root, entry)
    except LibraryError as exc:
        return None, [str(exc)], notes
    accepted = meta["status"] in STATES_ACCEPTED
    leftovers = sorted(p.name for p in entry.iterdir() if p.is_dir() and p.name.startswith(LEFTOVER_PREFIXES))
    if leftovers:
        notes.append(f"发现中断运行留下的临时目录（不影响已提交产物，可删除）：{', '.join(leftovers[:4])}")
    for label, value in metadata_paths(meta):
        try:
            path = internal(entry, value)
            if not path.is_file():
                if accepted and label not in {"assets.comparison"}:
                    errors.append(f"{label} 缺少文件：{value}")
                else:
                    notes.append(f"{label} 尚未生成：{value}")
        except LibraryError as exc:
            errors.append(str(exc))
    try:
        source_check(entry, meta)
    except LibraryError as exc:
        errors.append(str(exc))
    style, contract = None, None
    for schema_name, relative in (("style", meta["implementation"]["style"]), ("data-contract", meta["data"]["contract"]), ("review", "review.yaml")):
        if relative is None:
            if accepted:
                errors.append(f"验收条目缺少 {schema_name} 路径")
            continue
        try:
            path = internal(entry, relative)
            if path.exists():
                content = read_yaml(path)
                check_schema(root, schema_name, content)
                if schema_name == "style":
                    style = content
                elif schema_name == "data-contract":
                    contract = content
            elif schema_name == "review" and accepted:
                errors.append("验收条目缺少 review.yaml")
        except LibraryError as exc:
            errors.append(str(exc))
    try:
        if meta["data"]["path"]:
            data_file = internal(entry, meta["data"]["path"])
            if data_file.exists():
                notes.extend(validate_csv(data_file, contract, accepted=accepted))
        elif accepted:
            errors.append("验收条目必须声明可复用的主 CSV 路径")
        language = meta["implementation"]["language"]
        relative = meta["implementation"]["entrypoint"]
        if relative:
            code = internal(entry, relative)
            if language == "python" and code.suffix.lower() != ".py":
                errors.append("Python entrypoint 必须是 .py 文件")
            if language == "r" and code.suffix.lower() != ".r":
                errors.append("R entrypoint 必须是 .R 或 .r 文件")
            if language == "python" and code.is_file():
                try:
                    ast.parse(code.read_text(encoding="utf-8"), filename=relative)
                except (SyntaxError, UnicodeError) as exc:
                    errors.append(f"Python 入口语法无效：{exc}")
        elif accepted:
            errors.append("验收条目必须声明绘图入口")
        for folder in ("code", "data"):
            safe_files(entry / folder, entry)
    except LibraryError as exc:
        errors.append(str(exc))
    for name in ("preview", "thumbnail"):
        relative = meta["assets"][name]
        if relative:
            try:
                path = internal(entry, relative)
                if path.is_file():
                    read_raster(path, png_only=True)
            except LibraryError as exc:
                errors.append(str(exc))
    run = None
    try:
        if (entry / "outputs" / "run.json").exists():
            run = verify_current_run(entry, meta)
        elif accepted:
            errors.append("验收条目缺少 outputs/run.json；请先运行 render")
    except LibraryError as exc:
        errors.append(str(exc))
    if accepted:
        for key, expected in CANONICAL_ASSETS.items():
            if meta["assets"][key] != expected:
                errors.append(f"验收条目的 assets.{key} 应指向 {expected}")
        if meta["data"]["kind"] == "unknown":
            errors.append("验收前必须确认数据为 original、digitized 或 synthetic")
        try:
            review = read_yaml(internal(entry, "review.yaml", required=True))
            check_schema(root, "review", review)
            if run:
                check_review(entry, meta, review, run)
        except LibraryError as exc:
            errors.append(str(exc))
    return meta, list(dict.fromkeys(errors)), list(dict.fromkeys(notes))


def require_valid(root: Path, entry: Path):
    meta, errors, _ = validate_entry(root, entry)
    if errors:
        raise LibraryError(f"{entry.name} 校验失败：\n  - " + "\n  - ".join(errors))
    return meta


def create_entry(root: Path, args):
    identifier = valid_id(args.identifier)
    for collection in ("figures", "examples"):
        if (root / collection / identifier).exists():
            raise LibraryError(f"ID 已存在：{identifier}")
    imports = []
    for value, is_reference in [(args.reference, True)] + [(p, False) for p in args.asset]:
        if value is None:
            continue
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise LibraryError(f"只能导入普通文件：{path.name}")
        imports.append((path, is_reference))
    template = root / "templates" / "entry"
    if not template.is_dir():
        raise LibraryError("仓库缺少 templates/entry")
    destination = root / "figures" / identifier
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{identifier}.new-", dir=destination.parent))
    try:
        shutil.copytree(template, staging, dirs_exist_ok=True)
        for folder in ("reference", "outputs"):
            (staging / folder).mkdir(exist_ok=True)
        meta = read_yaml(staging / "figure.yaml")
        meta.update(id=identifier, title=args.title, created=date.today().isoformat())
        meta["source"]["kind"] = args.source_kind
        for index, (path, is_reference) in enumerate(imports, 1):
            extension = path.suffix.lower()
            base = "source" + extension if is_reference else re.sub(r"[^\w.\-]", "-", path.name).strip(".-")
            base = base or f"asset-{index}{extension}"
            name = base
            counter = 2
            while (staging / "reference" / name).exists():
                name = f"{Path(base).stem}-{counter}{Path(base).suffix}"
                counter += 1
            target = staging / "reference" / name
            shutil.copyfile(path, target)
            relative = f"reference/{name}"
            role = "code" if extension in {".py", ".r", ".ipynb", ".m", ".jl"} else "data" if extension in {".csv", ".tsv", ".xlsx", ".parquet"} else "image" if extension in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".svg", ".pdf"} else "caption" if extension in {".txt", ".md"} else "other"
            meta["source"]["files"].append({"path": relative, "sha256": sha256(target), "role": role})
            if is_reference:
                try:
                    read_raster(target)
                    meta["assets"]["reference"] = relative
                except LibraryError:
                    if extension in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}:
                        raise LibraryError("参考文件声称是位图，但实际不能解码；请检查原文件")
        check_schema(root, "figure", meta)
        write_yaml(staging / "figure.yaml", meta)
        readme = (staging / "README.md").read_text(encoding="utf-8").replace("{{ID}}", identifier).replace("{{TITLE}}", args.title)
        write_text(staging / "README.md", readme)
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def runtime_versions(entry: Path, meta, engine: str, executable: str):
    names = {"PyYAML", "Pillow", "jsonschema"}
    relative = meta["implementation"]["requirements"]
    if relative:
        for line in internal(entry, relative, required=True).read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*(?:[<>=!~\[;]|$)", line)
            if match:
                names.add(match.group(1))
    packages = {}
    for name in sorted(names, key=str.lower):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {"python": sys.version.split()[0], "packages": packages}
    if engine == "r":
        try:
            completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
            result["rscript"] = (completed.stdout or completed.stderr).strip()[:300]
        except (OSError, subprocess.TimeoutExpired):
            result["rscript"] = "unknown"
        result["r_package_versions"] = "not inspected; record in the entry when needed"
    return result


def run_process(argv, cwd: Path, timeout: float):
    try:
        process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=(os.name == "posix"))
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.communicate()
            raise LibraryError(f"绘图超过 {timeout:g} 秒，已终止；旧 outputs 保留")
        if process.returncode:
            detail = (stderr.strip() or stdout.strip() or "入口没有输出错误说明")[-6000:]
            raise LibraryError(f"绘图失败（退出码 {process.returncode}）；旧 outputs 保留。\n{detail}")
        return stdout, stderr
    except OSError as exc:
        raise LibraryError(f"无法启动绘图入口：{exc}") from exc


def verify_plot_outputs(staging: Path):
    for path in staging.rglob("*"):
        if path.is_symlink():
            raise LibraryError("绘图产物不能含符号链接；旧 outputs 保留")
    png = internal(staging, "figure.png", required=True)
    read_raster(png, png_only=True)
    svg = internal(staging, "figure.svg", required=True)
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(svg).getroot()
        if root.tag.split("}")[-1] != "svg":
            raise LibraryError("figure.svg 的根节点不是 SVG")
    except (ET.ParseError, OSError) as exc:
        raise LibraryError(f"figure.svg 不是可解析的矢量文件：{exc}") from exc
    pdf = staging / "figure.pdf"
    if pdf.exists():
        with pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise LibraryError("figure.pdf 不是 PDF 文件")
    thumb = read_raster(png, png_only=True)
    thumb.thumbnail((640, 480), Image.Resampling.LANCZOS)
    thumb.save(staging / "thumb.png", format="PNG")


def commit_directory(staging: Path, target: Path, *, replace=False, after_commit=None):
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise LibraryError("输出目标必须是普通目录，不能是文件或符号链接")
    if target.exists() and not replace:
        raise LibraryError(f"输出目录已存在：{target.name}；请选择新的目录")
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    had_old = target.exists()
    if had_old:
        os.rename(target, backup)
    installed = False
    try:
        os.rename(staging, target)
        installed = True
        if after_commit is not None:
            # Metadata uses an atomic file replace. Keep old outputs until it succeeds.
            after_commit()
    except BaseException:
        if installed:
            shutil.rmtree(target)
        if had_old:
            os.rename(backup, target)
        raise
    if had_old:
        try:
            shutil.rmtree(backup)
        except OSError:
            print(f"提示：新结果已提交，旧备份目录待手工清理：{backup.name}", file=sys.stderr)


def render_entry(root: Path, entry: Path, args):
    # Rendering is an explicit execution action. It is not a sandbox for untrusted code.
    meta = metadata(root, entry)
    for _, value in metadata_paths(meta):
        internal(entry, value)
    source_check(entry, meta)
    engine = meta["implementation"]["language"]
    relative = meta["implementation"]["entrypoint"]
    if engine not in {"python", "r"} or relative is None:
        raise LibraryError("仅支持显式运行 Python 或 R 入口；其他语言可收藏并手工执行")
    code = internal(entry, relative, required=True)
    if (engine == "python" and code.suffix.lower() != ".py") or (engine == "r" and code.suffix.lower() != ".r"):
        raise LibraryError("入口扩展名与 implementation.language 不一致")
    executable = sys.executable if engine == "python" else shutil.which("Rscript")
    if not executable:
        raise LibraryError("未找到 Rscript；请自行安装 R 及该条目依赖，CLI 不会自动安装")
    if args.timeout <= 0:
        raise LibraryError("--timeout 必须大于 0")
    data_override = Path(args.data).expanduser().resolve() if args.data else None
    style_override = Path(args.style).expanduser().resolve() if args.style else None
    if (data_override or style_override) and not args.out:
        raise LibraryError("使用 --data 或 --style 必须同时指定条目目录以外的 --out，保护已归档模板")
    for override in (data_override, style_override):
        if override and not override.is_file():
            raise LibraryError(f"覆盖输入不是文件：{override.name}")
    canonical = not args.out
    target = entry / "outputs" if canonical else target_new_directory(root, args.out)
    if not canonical:
        if target.is_relative_to(entry.resolve()):
            raise LibraryError("变体 --out 必须位于整个条目目录以外，不能覆盖 code/data/reference/outputs")
        if target.exists():
            raise LibraryError("变体 --out 已存在；请选择新的目录，避免覆盖先前结果")
    style_file = style_override or internal(entry, meta["implementation"]["style"], required=True)
    style = read_yaml(style_file)
    check_schema(root, "style", style)
    contract = None
    if meta["data"]["contract"]:
        contract = read_yaml(internal(entry, meta["data"]["contract"], required=True))
        check_schema(root, "data-contract", contract)
    data_file = data_override or internal(entry, meta["data"]["path"], required=True)
    validate_csv(data_file, contract)
    before = input_snapshot(entry, meta, data_override, style_override)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise LibraryError("输出目标不能是符号链接")
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.render-", dir=target.parent))
    try:
        actual_argv = [str(executable), relative, "--data", str(data_override) if data_override else meta["data"]["path"], "--style", str(style_override) if style_override else meta["implementation"]["style"], "--out", str(staging)]
        stdout, stderr = run_process(actual_argv, entry, args.timeout)
        if stdout.strip():
            print(stdout.strip()[-8000:])
        if stderr.strip():
            print("绘图入口提示（字体替换/字形等警告需检查）：\n" + stderr.strip()[-12000:], file=sys.stderr)
        verify_plot_outputs(staging)
        after = input_snapshot(entry, meta, data_override, style_override)
        source_check(entry, meta)
        if before != after:
            raise LibraryError("绘图运行期间输入文件发生变化，未替换旧 outputs；请检查入口代码")
        outputs = {}
        for path in safe_files(staging, staging):
            if path.name != "run.json":
                outputs[path.relative_to(staging).as_posix()] = sha256(path)
        normalized_argv = ["python" if engine == "python" else "Rscript", relative, "--data", f"external/{data_override.name}" if data_override else meta["data"]["path"], "--style", f"external/{style_override.name}" if style_override else meta["implementation"]["style"], "--out", "outputs" if canonical else "variant-output"]
        run = {
            "schema_version": 1, "entry_id": meta["id"], "run_id": uuid.uuid4().hex,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "success": True,
            "output_mode": "canonical" if canonical else "variant", "argv": normalized_argv,
            "argv_note": "Paths are normalized for portability. Execution uses an entry-relative working directory, the current interpreter, and a temporary output directory that is committed only after validation. External inputs are recorded by basename and hash.",
            "inputs": before, "input_sha256": object_sha256(before), "metadata_basis": metadata_basis(meta), "basis_sha256": object_sha256(metadata_basis(meta)), "recipe_sha256": recipe_digest(before, metadata_basis(meta)), "data_sha256": data_digest(before),
            "outputs": dict(sorted(outputs.items())), "runtime": runtime_versions(entry, meta, engine, str(executable)),
            "declared_seed": style.get("seed", style.get("random_seed")),
        }
        write_text(staging / "run.json", json_text(run))
        if canonical:
            meta["status"] = "draft"
            meta["assets"].update(CANONICAL_ASSETS)
            meta["assets"]["comparison"] = None
            commit_directory(staging, target, replace=True, after_commit=lambda: write_yaml(entry / "figure.yaml", meta))
        else:
            commit_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def compare_entry(root: Path, entry: Path):
    meta = metadata(root, entry)
    source_check(entry, meta)
    reference = meta["assets"]["reference"]
    if not reference:
        raise LibraryError("未声明位图参考。请先把 PDF/SVG 的目标图转为独立位图，保留来源并记录 SHA-256")
    verify_current_run(entry, meta)
    reference_image = read_raster(internal(entry, reference, required=True))
    reproduction = read_raster(internal(entry, meta["assets"]["preview"], required=True), png_only=True)
    # Uniform scaling only; each image keeps its own aspect ratio. This is diagnostic, not a score.
    cell_width, cell_height, padding, label_height = 1000, 800, 24, 42
    def panel(image):
        image = image.copy()
        factor = min(cell_width / image.width, cell_height / image.height)
        image = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (cell_width, cell_height), "white")
        canvas.alpha_composite(image, ((cell_width - image.width) // 2, (cell_height - image.height) // 2))
        return canvas.convert("RGB")
    left, right = panel(reference_image), panel(reproduction)
    canvas = Image.new("RGB", (2 * cell_width + 3 * padding, cell_height + label_height + 2 * padding), "#ececec")
    canvas.paste(left, (padding, padding + label_height))
    canvas.paste(right, (2 * padding + cell_width, padding + label_height))
    draw = ImageDraw.Draw(canvas)
    draw.text((padding, padding + 10), "REFERENCE (aspect ratio preserved)", fill="#222222")
    draw.text((2 * padding + cell_width, padding + 10), "REPRODUCTION (aspect ratio preserved)", fill="#222222")
    target = internal(entry, "outputs/comparison.png")
    target.parent.mkdir(exist_ok=True)
    temp = target.with_name(f".comparison-{uuid.uuid4().hex}.png")
    try:
        canvas.save(temp, format="PNG")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    meta["assets"]["comparison"] = "outputs/comparison.png"
    write_yaml(entry / "figure.yaml", meta)
    return target


def context_text(root: Path, entry: Path, meta, *, standalone=False) -> str:
    prefix = "" if standalone else entry.relative_to(root).as_posix() + "/"
    command = f"python scripts/figurelib.py render {meta['id']} --data /path/to/new.csv --out workspace/{meta['id']}-variant"
    if standalone:
        runner = {"python": "python", "r": "Rscript"}.get(meta["implementation"]["language"])
        command = f"{runner} {meta['implementation']['entrypoint']} --data {meta['data']['path']} --style {meta['implementation']['style']} --out variant" if runner else "# 按 README.md 中该语言的说明手动执行入口"
    parts = [f"# {meta['title']}\n", f"ID: `{meta['id']}` · kind: `{meta['kind']}` · status: `{meta['status']}` · data: `{meta['data']['kind']}`\n", f"收藏理由：{meta['why_saved'] or '尚未填写'}\n", "## 只读取这个条目\n"]
    for label, relative in [("元数据", "figure.yaml"), ("说明", "README.md"), ("样式", meta["implementation"]["style"]), ("数据契约", meta["data"]["contract"]), ("绘图代码", meta["implementation"]["entrypoint"]), ("依赖", meta["implementation"]["requirements"]), ("示例数据", meta["data"]["path"]), ("参考图", meta["assets"]["reference"]), ("输出预览", meta["assets"]["preview"]), ("审核", "review.yaml")]:
        if relative:
            path = internal(entry, relative)
            parts.append(f"- {label}: `{prefix}{relative}`{'（待补齐）' if not path.exists() else ''}")
    parts += ["\n## 数据与使用边界\n", meta["data"]["notes"] or "尚未补充数值来源说明。", "\n" + "; ".join(meta["reuse"]["caveats"] or ["未声明复用限制，使用前仍需核对数据契约。"])]
    if meta["kind"] == "example":
        parts.append("\n这是明确分开的演示条目，不能说成来自外部论文的真实收藏。")
    for title, relative, limit in [("样式摘要", meta["implementation"]["style"], 2600), ("数据契约摘要", meta["data"]["contract"], 3400)]:
        if relative:
            path = internal(entry, relative)
            if path.is_file():
                contents = path.read_text(encoding="utf-8")
                excerpt = contents[:limit] + ("\n# ……完整内容见上面的文件路径\n" if len(contents) > limit else "")
                parts.append(f"\n## {title}\n\n```yaml\n{excerpt.rstrip()}\n```\n")
    parts += ["## 换数据运行\n", f"```bash\n{command}\n```", "\n先审查入口，再显式运行。保持原始材料和已归档结果；实际查看新图后分别检查布局与数值。"]
    return "\n".join(parts) + "\n"


def catalog_record(root: Path, entry: Path, meta):
    prefix = entry.relative_to(root).as_posix()
    def existing(relative):
        return f"{prefix}/{relative}" if relative and internal(entry, relative).is_file() else None
    style = read_yaml(internal(entry, meta["implementation"]["style"], required=True)) if meta["implementation"]["style"] and internal(entry, meta["implementation"]["style"]).is_file() else {}
    return {"id": meta["id"], "title": meta["title"], "kind": meta["kind"], "status": meta["status"], "family": meta["family"], "tags": meta["tags"], "why_saved": meta["why_saved"], "data_kind": meta["data"]["kind"], "palette": style.get("palette", {}),
            "paths": {"entry": prefix, "metadata": f"{prefix}/figure.yaml", "readme": existing("README.md"), "style": existing(meta["implementation"]["style"]), "contract": existing(meta["data"]["contract"]), **{key: existing(meta["assets"][key]) for key in ("preview", "thumbnail", "vector", "reference", "comparison")}}}


def build_catalog(root: Path, include_examples=False):
    selected = entries(root, include_examples)
    records = [catalog_record(root, entry, require_valid(root, entry)) for entry in selected]
    catalog = {"api_version": 1, "entries": records}
    check_schema(root, "catalog", catalog)
    text = ["# 图表目录", "", "由 `figure.yaml` 生成；请在条目中修改，再运行 `build`。", ""]
    if records:
        text += ["| 预览 | ID / 图名 | 类型 | 状态 | 数据 |", "| --- | --- | --- | --- | --- |"]
        for row in records:
            thumbnail = row["paths"]["thumbnail"]
            if thumbnail:
                preview = f"![{row['id']}](../{thumbnail})"
            elif row["paths"]["reference"] and row["status"] in {"captured", "draft"}:
                preview = f"![参考原图 {row['id']}](../{row['paths']['reference']})<br>参考原图（尚未生成复现预览）"
            else:
                preview = "待绘图"
            title = html.escape(row["title"]).replace("|", "\\|").replace("\n", " ")
            family = html.escape(row["family"]).replace("|", "\\|")
            text.append(f"| {preview} | [`{row['id']}`](../{row['paths']['metadata']})<br>{title} | {family} | {row['status']} | {row['data_kind']} |")
    else:
        text += ["真实收藏目前为空。`examples/` 中的演示不会自动进入这里。", "", "需要查看演示时，显式运行 `python scripts/figurelib.py build --include-examples`。"]
    write_text(root / "catalog" / "catalog.json", json_text(catalog))
    write_text(root / "catalog" / "GALLERY.md", "\n".join(text) + "\n")
    return len(records)


def target_new_directory(root: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise LibraryError("输出目录不能是符号链接")
    target = raw.resolve()
    if target.exists():
        raise LibraryError("输出目录已存在；请指定新的空位置，避免覆盖或残留旧文件")
    for folder in (root / "figures", root / "examples", root / "templates", root / "schema", root / "scripts"):
        if target.is_relative_to(folder.resolve()):
            raise LibraryError("输出目录不能位于仓库的条目、模板或程序目录内")
    return target


def bundle_entry(root: Path, entry: Path, value: str):
    meta = require_valid(root, entry)
    target = target_new_directory(root, value)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.bundle-", dir=target.parent))
    def ignore(folder, names):
        excluded = []
        for name in names:
            path = Path(folder) / name
            if name in IGNORED_DIRS or name in IGNORED_FILES or name.endswith((".pyc", ".pyo", ".tmp")) or name.startswith((".render-", ".outputs.render-", ".outputs.backup-")):
                excluded.append(name)
            elif path.is_symlink():
                raise LibraryError("独立导出不支持符号链接，请先将条目依赖变成实际文件")
        return excluded
    try:
        shutil.copytree(entry, staging, dirs_exist_ok=True, ignore=ignore)
        brief = context_text(root, entry, meta, standalone=True)
        brief += "\n## 独立目录\n\n此目录已包含所选条目文件，可在此目录运行绘图入口；不需要仓库 CLI。依赖见 `code/requirements.txt`。换数据时使用新的输出目录。\n\n这份完整导出包含参考材料和数据，请按本地/私有协作材料处理。公开图片请回到仓库使用 `export-public` 的白名单导出。\n"
        write_text(staging / "AGENT_BRIEF.md", brief)
        commit_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def safe_png(source: Path, target: Path):
    decoded = read_raster(source, png_only=True)
    # A new pixel-only image discards EXIF, comments, software fields, profiles and text chunks.
    clean = Image.frombytes("RGBA", decoded.size, decoded.tobytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    clean.save(target, format="PNG")


def export_public(root: Path, value: str):
    target = target_new_directory(root, value)
    approved = []
    for entry in entries(root, include_examples=False):
        meta = metadata(root, entry)
        if not meta["publication"]["include_in_public_catalog"]:
            continue
        if meta["status"] not in STATES_ACCEPTED:
            raise LibraryError(f"{meta['id']} 已勾选公开，但尚未经过 reproduced/reusable 审核")
        if not meaningful(meta["publication"]["rights_note"], 8):
            raise LibraryError(f"{meta['id']} 缺少明确的 publication.rights_note")
        require_valid(root, entry)
        approved.append((entry, meta))
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.public-", dir=target.parent))
    records = []
    try:
        for entry, meta in approved:
            palette = read_yaml(internal(entry, meta["implementation"]["style"], required=True))["palette"]
            record = {"id": meta["id"], "title": meta["title"], "family": meta["family"], "tags": meta["tags"], "status": meta["status"], "data_kind": meta["data"]["kind"], "palette": palette}
            for field, filename in (("preview", "preview.png"), ("thumbnail", "thumb.png")):
                if meta["assets"][field] != CANONICAL_ASSETS[field]:
                    raise LibraryError("公开图像必须来自已审核的 outputs/figure.png 与 outputs/thumb.png")
                relative = f"assets/{meta['id']}/{filename}"
                safe_png(internal(entry, meta["assets"][field], required=True), staging / relative)
                record[field] = relative
            records.append(record)
        write_text(staging / "catalog.json", json_text({"api_version": 1, "entries": records}))
        commit_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target, len(records)


def load_site_module():
    spec = importlib.util.spec_from_file_location("figurelib_site", Path(__file__).resolve().with_name("figurelib_site.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def site_command(root: Path, args):
    site = load_site_module()
    # Pass this module's own helpers so exceptions and constants stay identical.
    core = types.SimpleNamespace(**globals())
    include = True if args.include_examples else (False if args.no_examples else None)
    target, records, problems = site.build_site(core, root, out=args.out, local=args.local, include_examples=include)
    label = "本地管理视图（含草稿与参考图，勿发布）" if args.local else "公开网页"
    print(f"已生成{label}：{target}\n共 {len(records)} 条" + (f"，{len(problems)} 个无法读取的条目" if problems else "") + "。")
    if args.serve is not None:
        site.serve(target, args.serve)
    elif args.local:
        print(f"浏览：python scripts/figurelib.py site --local --serve  或  python -m http.server -d {target} 8000")


def make_parser():
    parser = argparse.ArgumentParser(description="按 ID 收藏、复现与复用科研图表；不会自动检索整个图库或运行外部代码。")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="创建真实收藏条目并原样保存材料")
    new.add_argument("identifier", metavar="ID")
    new.add_argument("--title", required=True, help="图表名称")
    new.add_argument("--reference", help="参考图文件；PDF/SVG 原件可保存，但对照需要另备位图")
    new.add_argument("--asset", action="append", default=[], help="追加材料文件，可重复；代码只收藏，不执行")
    new.add_argument("--source-kind", choices=["unknown", "self", "paper", "web"], default="unknown")
    for command, description in (("show", "显示所选条目的元数据"), ("context", "输出仅针对所选 ID 的 Agent 上下文"), ("compare", "生成保持长宽比的参考图/复现图并排对照")):
        child = sub.add_parser(command, help=description)
        child.add_argument("identifier", metavar="ID")
    list_parser = sub.add_parser("list", help="列出真实收藏；演示须显式加入")
    list_parser.add_argument("--include-examples", action="store_true")
    validate = sub.add_parser("validate", help="检查结构、源指纹、运行状态与审核绑定")
    validate.add_argument("identifier", metavar="ID", nargs="?")
    validate.add_argument("--include-examples", action="store_true")
    render = sub.add_parser("render", help="显式运行已审查的入口，验证成功后再替换 outputs")
    render.add_argument("identifier", metavar="ID")
    render.add_argument("--data", help="替换 CSV；必须配合外部 --out")
    render.add_argument("--style", help="替换样式；必须配合外部 --out")
    render.add_argument("--out", help="条目目录之外的新变体目录；省略则更新主 outputs")
    render.add_argument("--timeout", type=float, default=120, help="运行时限，秒；默认 120")
    build = sub.add_parser("build", help="重建 catalog.json 和 Markdown 目录（网页用 site）")
    build.add_argument("--include-examples", action="store_true")
    bundle = sub.add_parser("bundle", help="导出一个无仓库依赖的完整私有条目")
    bundle.add_argument("identifier", metavar="ID")
    bundle.add_argument("--out", required=True, help="新的独立目录")
    site = sub.add_parser("site", help="生成静态网页：默认公开模式（GitHub Pages），--local 为私有管理视图")
    site.add_argument("--out", help="输出目录；默认公开模式为 _site/，本地模式为 workspace/site-local/")
    site.add_argument("--local", action="store_true", help="包含全部条目、草稿、参考图与校验问题，仅供本机查看")
    group = site.add_mutually_exclusive_group()
    group.add_argument("--include-examples", action="store_true", help="覆盖 site.config.json，加入示例")
    group.add_argument("--no-examples", action="store_true", help="覆盖 site.config.json，不加入示例")
    site.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT", help="生成后在 127.0.0.1 启动预览服务器")
    public = sub.add_parser("export-public", help="只导出明确批准的 PNG 预览、缩略图与白名单 JSON")
    public.add_argument("--out", required=True, help="新的公开导出目录")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        command = args.command
        if command == "new":
            target = create_entry(root, args)
            print(f"已创建 figures/{target.name}（captured）。材料已保存；绘图入口仍是待实现脚手架。")
        elif command in {"show", "context", "render", "compare", "bundle"}:
            entry = resolve_entry(root, args.identifier)
            if command == "show":
                print(yaml.safe_dump(metadata(root, entry), allow_unicode=True, sort_keys=False), end="")
            elif command == "context":
                print(context_text(root, entry, metadata(root, entry)), end="")
            elif command == "render":
                target = render_entry(root, entry, args)
                print(f"绘图完成：{target}")
                print("主条目保持 draft，需实际检查后重新绑定审核。" if not args.out else "变体已保存；未改变主条目的代码、数据、输出或审核。")
            elif command == "compare":
                print(f"已生成对照：{compare_entry(root, entry)}\n这是诊断图，不是自动相似度评分。")
            else:
                print(f"已导出独立条目：{bundle_entry(root, entry, args.out)}")
        elif command == "list":
            selected = entries(root, args.include_examples)
            print("ID\tfamily\tstatus\tdata\ttitle")
            for entry in selected:
                meta = metadata(root, entry)
                print("\t".join([meta["id"], meta["family"], meta["status"], meta["data"]["kind"], meta["title"].replace("\n", " ").replace("\t", " ")]))
            print(f"共 {len(selected)} 条" + ("（含演示）" if args.include_examples else "真实收藏"))
        elif command == "validate":
            selected = [resolve_entry(root, args.identifier)] if args.identifier else entries(root, args.include_examples)
            failed = 0
            for entry in selected:
                _, errors, notes = validate_entry(root, entry)
                print(f"{'未通过' if errors else '通过'} {entry.name}")
                for error in errors:
                    print(f"  错误：{error}")
                for note in notes[:8]:
                    print(f"  待补：{note}")
                failed += bool(errors)
            print(f"已校验 {len(selected)} 条，{failed} 条未通过。视觉质量与科学含义仍需实际检查。")
            return 1 if failed else 0
        elif command == "build":
            print(f"已生成 catalog/catalog.json 与 catalog/GALLERY.md，共 {build_catalog(root, args.include_examples)} 条。")
        elif command == "site":
            site_command(root, args)
        elif command == "export-public":
            target, count = export_public(root, args.out)
            print(f"已导出 {count} 条明确批准的公开预览：{target}")
        return 0
    except (LibraryError, OSError, UnicodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
