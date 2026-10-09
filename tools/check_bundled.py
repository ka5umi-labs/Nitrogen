#!/usr/bin/env python3
"""
check_bundled.py —— 打包分发模组的校验

背景
================================================================
Modrinth 只接受来自 cdn.modrinth.com 的下载链接（packwiz 的白名单
还含 github.com / gitlab.com / raw.githubusercontent.com，但实践上
CurseForge 链接一定不行）。凡是不在 Modrinth 上的模组，都必须把
jar 直接打包进 mrpack。

做法是把 jar 放在 `mods/` 目录下（**不是** overrides/ —— 放那里会
被导出成 overrides/overrides/，玩家装了不生效，已实测确认）。
`bundled-mods.toml` 记录每个 jar 的来源与更新方式。

本工具检查：
  1. 每个 jar 都在 bundled-mods.toml 里有登记（否则下次无人知道来源）
  2. 每条登记的 file 都真实存在于 mods/
  3. jar 的 sha256 与 index.toml 一致
  4. 没有 jar 被误放进 overrides/（会双重嵌套）
  5. 许可证风险提示（ARR 模组再分发需授权）
  6. jar 内的 side 与登记一致

用法
================================================================
    python3 tools/check_bundled.py
    python3 tools/check_bundled.py --json out.json

退出码：0 无问题；1 存在错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packwiz_common as pc  # noqa: E402

MANIFEST = "bundled-mods.toml"
# 再分发前需要作者授权的许可证
RESTRICTIVE = {"ARR", "arr", "All-Rights-Reserved", "proprietary"}

errors, warnings = [], []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def parse_manifest():
    """解析 bundled-mods.toml，返回 [[mod]] 条目列表。"""
    path = os.path.join(pc.ROOT, MANIFEST)
    if not os.path.isfile(path):
        return None
    mods, cur = [], None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line == "[[mod]]":
            cur = {}
            mods.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r'^([a-z_]+)\s*=\s*"?(.*?)"?$', line)
        if m:
            cur[m.group(1)] = m.group(2)
    return mods


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def index_hashes():
    """从 index.toml 读取 file -> sha256 映射。"""
    p = os.path.join(pc.ROOT, "index.toml")
    if not os.path.isfile(p):
        return {}
    raw = open(p, encoding="utf-8").read()
    return {m.group(1): m.group(2) for m in re.finditer(
        r'\[\[files\]\]\s*\nfile = "((?:[^"\\]|\\.)*)"\s*\nhash = "([0-9a-f]+)"', raw)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()

    print("== check_bundled.py ==\n")

    manifest = parse_manifest()
    if manifest is None:
        print(f"! 找不到 {MANIFEST}")
        return 1

    mods_dir = os.path.join(pc.ROOT, "mods")
    jars_on_disk = sorted(
        f for f in os.listdir(mods_dir) if f.endswith((".jar", ".litemod"))
    ) if os.path.isdir(mods_dir) else []

    registered = {m.get("file"): m for m in manifest if m.get("file")}

    print(f"  登记模组 {len(registered)} 个 / 磁盘上 jar {len(jars_on_disk)} 个\n")

    # --- 1 & 2. 双向覆盖检查 ---
    for f in jars_on_disk:
        if f not in registered:
            err(f"mods/{f} 未在 {MANIFEST} 中登记"
                f" —— 请补充来源信息，否则后续无人知道如何更新")
    for f in registered:
        if f not in jars_on_disk:
            err(f"{MANIFEST} 登记的 mods/{f} 在磁盘上不存在")

    # --- 3. 哈希与 index 一致性 ---
    idx = index_hashes()
    for f in jars_on_disk:
        rel = f"mods/{f}"
        actual = sha256_of(os.path.join(mods_dir, f))
        if rel not in idx:
            err(f"{rel} 不在 index.toml 中（应执行 packwiz refresh）")
        elif idx[rel] != actual:
            err(f"{rel} 的哈希与 index.toml 不一致"
                f"（应执行 packwiz refresh）")

    # --- 4. overrides/ 误放检查 ---
    for sub in ("overrides", "client-overrides", "server-overrides"):
        d = os.path.join(pc.ROOT, sub)
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith((".jar", ".litemod")):
                    err(f"{os.path.relpath(os.path.join(root, f), pc.ROOT)} "
                        f"放在 {sub}/ 下会被导出为 {sub}/{sub}/...，"
                        f"玩家装了不生效。请移到 mods/ 下")

    # --- 5 & 6. 许可证与 side 检查 ---
    for f in jars_on_disk:
        rel = f"mods/{f}"
        full = os.path.join(mods_dir, f)
        info = registered.get(f, {})
        lic = info.get("license", "")

        if lic in RESTRICTIVE:
            warn(f"{f}: 许可证为 {lic}（保留所有权利）。"
                 f"打包进 Modrinth 属于再分发，建议确认已获作者授权")

        fj = pc.read_fabric_json(full)
        if fj:
            env = fj.get("environment", "*")
            exp_side = {"client": "client", "server": "server",
                        "*": "both"}.get(env)
            declared = info.get("side")
            if exp_side and declared and exp_side != declared:
                err(f"{f}: 登记的 side=\"{declared}\" 与 jar 的 "
                    f"environment=\"{env}\" 不一致（应为 \"{exp_side}\"）")

        if not info.get("source_url"):
            warn(f"{f}: 未登记来源 URL，后续难以追踪更新")

    print()
    if warnings:
        print(f"提示 {len(warnings)} 条:")
        for w in warnings:
            print("  ! " + w)
        print()
    if errors:
        print(f"错误 {len(errors)} 条:")
        for e in errors:
            print("  x " + e)
        print("\n结果: 失败")
        return 1

    print("结果: 通过")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"errors": errors, "warnings": warnings,
                       "bundled": list(registered)}, fh,
                      ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
