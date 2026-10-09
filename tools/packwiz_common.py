#!/usr/bin/env python3
"""
packwiz_common.py —— tools/ 下各脚本共用模块

提供：
  * .pw.toml 的轻量解析（不依赖第三方库）
  * 遍历仓库内的元数据文件
  * jar 的下载与哈希校验（带本地缓存）
  * 读取 jar 内的 fabric.mod.json
  * 通过 git 判断本次改动涉及的元数据文件
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile

USER_AGENT = "nitrogen-tools/1.0 (+https://modrinth.com/modpack/nitrogen7)"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# jar 缓存目录。CI 中可把它设为工作区内的路径并交给 actions/cache 缓存。
CACHE_DIR = os.environ.get("NITROGEN_JAR_CACHE") or os.path.join(
    os.path.expanduser("~"), ".cache", "nitrogen-tools", "jars"
)

HASH_LEN = {"sha512": 128, "sha256": 64, "sha1": 40, "md5": 32}
VALID_SIDE = ("client", "server", "both")

# 这些目录不属于模组元数据，遍历时跳过
SKIP_DIRS = {".git", "tools", "node_modules", ".cache", ".github"}


def hash_file(path, algo="sha256"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path):
    return hash_file(path, "sha256")


def parse_pw_toml(path):
    """解析 .pw.toml，返回 dict。

    顶层标量放在 data 下；[download] 放在 data["download"]；
    [update.<source>] 放在 data["update"][<source>]。
    """
    data = {"download": {}, "update": {}}
    section = None
    sub = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                name = line.strip("[]")
                parts = name.split(".")
                if len(parts) == 1:
                    section, sub = parts[0], None
                    if section in ("download", "update"):
                        data[section] = {}
                elif parts[0] == "update":
                    section, sub = "update", parts[1]
                    data["update"].setdefault(sub, {})
                else:
                    section, sub = parts[-1], None
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"')
            if section == "download":
                data["download"][k] = v
            elif section == "update" and sub:
                data["update"][sub][k] = v
            elif section is None:
                data[k] = v
    return data


def iter_meta(prefixes=("mods/",)):
    """遍历指定前缀下的所有 .pw.toml，返回 [(相对路径, 解析结果)]。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".pw.toml"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT) \
                     .replace(os.sep, "/")
            if prefixes and not any(rel.startswith(p) for p in prefixes):
                continue
            out.append((rel, parse_pw_toml(os.path.join(ROOT, rel))))
    return sorted(out)


def fetch_jar(rel, data):
    """下载并校验 jar，返回本地缓存路径。已缓存且哈希正确则复用。"""
    dl = data.get("download", {})
    url = dl.get("url")
    hf = dl.get("hash-format") or "sha512"
    hv = dl.get("hash")
    if not url or not hv:
        raise ValueError(f"{rel}: 元数据缺少 url 或 hash")

    key = hashlib.sha256(f"{url}|{hv}".encode()).hexdigest()[:32]
    path = os.path.join(CACHE_DIR, key + ".jar")

    if os.path.isfile(path) and hash_file(path, hf) == hv:
        return path

    os.makedirs(CACHE_DIR, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = path + ".part"
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        got = hash_file(tmp, hf)
        if got != hv:
            raise ValueError(
                f"{rel}: 下载内容哈希不匹配\n      期望 {hv}\n      实际 {got}"
            )
        os.replace(tmp, path)
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)
    return path


def read_fabric_json(jar_path):
    """读取 jar 内的 fabric.mod.json；非 Fabric 模组返回 None。"""
    try:
        with zipfile.ZipFile(jar_path) as z:
            if "fabric.mod.json" not in z.namelist():
                return None
            return json.loads(z.read("fabric.mod.json"))
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return None


def git_changed_meta(base=None):
    """返回本次改动涉及的 .pw.toml 列表；git 不可用时返回 None。

    按以下顺序尝试，任一成功即返回（取并集会更准确，但这里以最贴近
    当前上下文的结果为准）：

      1. 工作区 + 暂存区未提交的改动（本地开发、CI 的 pull_request）
      2. 相对 base（默认 origin/main）的已提交改动（CI 的 push 事件）
      3. HEAD~1（本地刚提交完）

    注意：在 PR 场景下改动往往尚未提交到任何分支外，此时 1 是唯一
    能命中的来源，因此它必须排在最前。
    """
    env_base = os.environ.get("GITHUB_BASE_REF")

    # 1. 未提交改动（工作区 + 暂存区）
    for args in (["diff", "--name-only", "HEAD"],
                 ["diff", "--name-only", "--cached"],
                 ["diff", "--name-only"]):
        r = _try_git(args)
        if r:
            return r

    # 2. 相对 base 的已提交改动
    bases = []
    if base:
        bases.append(base)
    if env_base:
        bases.append(f"origin/{env_base}")
    bases += ["origin/main", "origin/master"]
    for b in bases:
        if _rev_exists(b):
            r = _try_git(["diff", "--name-only", f"{b}...HEAD"])
            if r:
                return r

    # 3. 上一个提交
    r = _try_git(["diff", "--name-only", "HEAD~1"])
    if r:
        return r

    return None


def _try_git(args):
    """执行 git 命令，返回 .pw.toml 文件列表；无输出或失败返回 None。"""
    try:
        r = subprocess.run(["git"] + args, cwd=ROOT,
                           capture_output=True, text=True, check=True)
    except Exception:
        return None
    files = [l for l in r.stdout.splitlines() if l.endswith(".pw.toml")]
    return files or None


def _rev_exists(rev):
    try:
        subprocess.run(["git", "rev-parse", "--verify", rev],
                       cwd=ROOT, capture_output=True, check=True)
        return True
    except Exception:
        return False
