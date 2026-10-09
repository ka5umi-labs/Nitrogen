#!/usr/bin/env python3
"""
verify_pack.py —— packwiz 仓库一致性校验

检查项：
  1. 每个 .pw.toml 都能被解析，必填字段齐全
  2. index.toml 中每个条目的哈希与磁盘实际文件一致
  3. index.toml 覆盖了所有 .pw.toml，且没有多余条目
  4. pack.toml 里记录的 index.toml 哈希正确
  5. 远程下载地址可达（--online 时启用）

退出码：0 全部通过；1 存在错误。
用法：
    python3 tools/verify_pack.py            # 本地检查
    python3 tools/verify_pack.py --online   # 附带远程可达性
"""
import argparse
import concurrent.futures
import hashlib
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# .pw.toml 中允许出现的顶层键
ALLOWED_KEYS = {
    "name", "filename", "side", "pin", "download", "update", "option",
}
REQUIRED_KEYS = {"name", "filename", "download"}

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def parse_pw_toml(path):
    """轻量 TOML 解析：只处理 packwiz 生成的结构，不依赖第三方库。"""
    data = {"download": {}, "update": {}}
    section = None
    sub = None
    for raw in open(path, encoding="utf-8").read().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[[") or line.startswith("["):
            name = line.strip("[]")
            parts = name.split(".")
            if len(parts) == 1:
                section, sub = parts[0], None
                if section == "update":
                    data["update"] = {}
                elif section == "download":
                    data["download"] = {}
            elif parts[0] == "update":
                sub = parts[1]
                section = "update"
                data["update"].setdefault(sub, {})
            else:
                section, sub = parts[-1], None
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        v = v.strip('"')
        if section == "download":
            data["download"][k] = v
        elif section == "update" and sub:
            data["update"][sub][k] = v
        elif section == "update":
            continue
        elif section is None:
            data[k] = v
    return data


def collect_pw_tomls():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "node_modules", "tools")]
        for fn in filenames:
            if fn.endswith(".pw.toml"):
                full = os.path.join(dirpath, fn)
                out.append(os.path.relpath(full, ROOT).replace(os.sep, "/"))
    return sorted(out)


def check_metadata(rel):
    path = os.path.join(ROOT, rel)
    d = parse_pw_toml(path)

    for k in REQUIRED_KEYS:
        if not d.get(k):
            err(f"{rel}: 缺少必填字段 `{k}`")

    side = d.get("side", "")
    if side not in ("client", "server", "both", ""):
        err(f"{rel}: side 取值非法 `{side}`（应为 client/server/both 或省略）")

    dl = d.get("download", {})
    if not dl.get("url"):
        err(f"{rel}: [download] 缺少 url")
    if not dl.get("hash"):
        err(f"{rel}: [download] 缺少 hash")
    if not dl.get("hash-format"):
        err(f"{rel}: [download] 缺少 hash-format")

    # 验证 hash 与 url 文件名的一致性不能直接判断（哈希需下载），
    # 但可以检查 hash 长度是否与算法匹配
    hf, hv = dl.get("hash-format"), dl.get("hash", "")
    expect = {"sha512": 128, "sha256": 64, "sha1": 40, "md5": 32}
    if hf in expect and len(hv) != expect[hf]:
        err(f"{rel}: {hf} 哈希长度错误（期望 {expect[hf]}，实际 {len(hv)}）")

    # update 段落检查
    upd = d.get("update", {})
    mode = dl.get("mode", "")
    if mode == "metadata:curseforge":
        if "curseforge" not in upd:
            err(f"{rel}: mode 为 metadata:curseforge 但缺少 [update.curseforge]")
        else:
            for k in ("project-id", "file-id"):
                if not upd["curseforge"].get(k):
                    err(f"{rel}: [update.curseforge] 缺少 {k}")
    elif "modrinth" in upd:
        for k in ("mod-id", "version"):
            if not upd["modrinth"].get(k):
                err(f"{rel}: [update.modrinth] 缺少 {k}")
    elif "curseforge" in upd:
        for k in ("project-id", "file-id"):
            if not upd["curseforge"].get(k):
                err(f"{rel}: [update.curseforge] 缺少 {k}")
    else:
        # 无 update 段落：url 模式，通常是无法自动更新的模组
        url = dl.get("url", "")
        if "github.com" not in url:
            warn(f"{rel}: 无 [update] 且 url 非 GitHub Release，"
                 f"该模组无法自动更新")

    # filename 与 url 末段一致性
    fn = d.get("filename", "")
    url = dl.get("url", "")
    if fn and url:
        import urllib.parse
        tail = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        if tail != fn:
            warn(f"{rel}: filename `{fn}` 与 url 末段 `{tail}` 不一致")


def check_index():
    idx_path = os.path.join(ROOT, "index.toml")
    if not os.path.isfile(idx_path):
        err("index.toml 不存在")
        return None, {}

    raw = open(idx_path, encoding="utf-8").read()
    entries = {}
    for m in re.finditer(
        r'\[\[files\]\]\s*\nfile = "((?:[^"\\]|\\.)*)"\s*\nhash = "([0-9a-f]+)"',
        raw,
    ):
        entries[m.group(1)] = m.group(2)

    if not entries:
        err("index.toml 中没有任何 [[files]] 条目")

    for rel, declared in entries.items():
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            err(f"index.toml 引用了不存在的文件: {rel}")
            continue
        actual = hashlib.sha256(open(full, "rb").read()).hexdigest()
        if actual != declared:
            err(f"{rel}: index.toml 哈希不匹配（应执行 packwiz refresh）\n"
                f"      声明 {declared}\n      实际 {actual}")

    # index 与磁盘对照
    on_disk = set(collect_pw_tomls())
    in_index = set(entries)
    for rel in sorted(on_disk - in_index):
        err(f"{rel}: 存在于磁盘但不在 index.toml 中（应执行 packwiz refresh）")
    for rel in sorted(in_index - on_disk):
        err(f"{rel}: 在 index.toml 中但磁盘上不存在")

    # metafile 标记
    for m in re.finditer(
        r'\[\[files\]\]\s*\nfile = "((?:[^"\\]|\\.)*)"\s*\nhash = "[0-9a-f]+"\s*\n(metafile = true)?',
        raw,
    ):
        rel, mf = m.group(1), m.group(2)
        if rel.endswith(".pw.toml") and not mf:
            err(f"{rel}: 是元数据文件但 index.toml 中缺少 metafile = true")

    return idx_path, entries


def check_pack(idx_path):
    pack_path = os.path.join(ROOT, "pack.toml")
    if not os.path.isfile(pack_path):
        err("pack.toml 不存在")
        return
    raw = open(pack_path, encoding="utf-8").read()

    m = re.search(r'\[index\][^\[]*?hash = "([0-9a-f]+)"', raw, re.S)
    if not m:
        err("pack.toml 的 [index] 段缺少 hash")
        return
    declared = m.group(1)
    if idx_path and os.path.isfile(idx_path):
        actual = hashlib.sha256(open(idx_path, "rb").read()).hexdigest()
        if actual != declared:
            err("pack.toml 记录的 index.toml 哈希不正确\n"
                f"      声明 {declared}\n      实际 {actual}")

    for k in ("name", "author", "version", "pack-format"):
        if not re.search(rf'^{k} = ', raw, re.M):
            err(f"pack.toml 缺少 {k}")

    if not re.search(r'\[versions\]', raw):
        err("pack.toml 缺少 [versions] 段")


def check_downloads(entries):
    """并发检查所有下载地址可达。"""
    urls = []
    for rel in entries:
        d = parse_pw_toml(os.path.join(ROOT, rel))
        u = d.get("download", {}).get("url")
        if u:
            urls.append((rel, u))

    def probe(item):
        rel, url = item
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "nitrogen-verify/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return rel, url, r.status, r.headers.get("Content-Length")
        except Exception as e:
            return rel, url, None, str(e)

    bad = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for rel, url, status, extra in ex.map(probe, urls):
            if status is None or status >= 400:
                bad.append((rel, url, status, extra))
    for rel, url, status, extra in bad:
        err(f"{rel}: 下载地址不可达 ({status}) {url}\n      {extra}")
    print(f"  已探测 {len(urls)} 个下载地址，失败 {len(bad)} 个")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true",
                    help="附带检查下载地址可达性（较慢）")
    args = ap.parse_args()

    print("== verify_pack.py ==")

    pw = collect_pw_tomls()
    print(f"  发现 {len(pw)} 个 .pw.toml")

    for rel in pw:
        check_metadata(rel)

    idx_path, entries = check_index()
    check_pack(idx_path)

    if args.online and entries:
        check_downloads(entries)

    print()
    if warnings:
        print(f"警告 {len(warnings)} 条:")
        for w in warnings:
            print("  ! " + w)
    if errors:
        print(f"错误 {len(errors)} 条:")
        for e in errors:
            print("  x " + e)
        print("\n结果: 失败")
        return 1
    print("结果: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
