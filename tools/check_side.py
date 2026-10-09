#!/usr/bin/env python3
"""
check_side.py —— side 字段合理性检查

铁律要求：所有模组必须能被原版对端接受。`side` 字段决定 packwiz 在
服务端分发时是否安装该模组，写错会导致：

  side 写 "both" 但实际是纯客户端模组
      -> 在服务端装了客户端模组，可能报错或行为异常

  side 写 "client" 但实际需要双端
      -> 服务端拿不到必需组件，联机功能失效

判定依据（关键，勿轻改）
================================================================
权威依据是 **Modrinth 版本的 environment 字段**，这正是 packwiz 自己
用来算 side 的输入（见 modrinth/modrinth.go 的 getSide()）。本项目
生成 .pw.toml 时用的同一套映射，所以本工具实质是复核"生成的 side
是否忠实于上游数据"。

**不要**用 Modrinth 项目页的 client_side / server_side 判定：
那两个字段粒度粗得多，且与版本级字段经常互相矛盾（实测案例
zoomify：项目页 server=unsupported，但版本 environment 是
client_only_server_optional）。也不要用 jar 里的 fabric.mod.json：
`environment: "*"` 只表示 jar 两端都能被加载，纯客户端模组普遍这么写
（实测 clientcommands、durability-tooltip、extreme_sound_muffler
三个 side=client 的模组其 jar 都声明 env="*"）。

用法
================================================================
    python3 tools/check_side.py                  # 检查全部
    python3 tools/check_side.py --explain <rel>  # 单个模组详情
    python3 tools/check_side.py --json out.json

退出码：0 无不一致；1 存在不一致。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packwiz_common as pc  # noqa: E402

API = "https://api.modrinth.com/v2"

# 与 packwiz getSide() 完全一致的映射（modrinth/modrinth.go）
# https://modrinth.com/news/article/new-environments/
SIDE_MAP = {
    "client_only": "client",
    "server_only": "both",
    "dedicated_server_only": "server",
    "client_and_server": "both",
    "server_only_client_optional": "both",
    "client_only_server_optional": "both",
    "client_or_server_prefers_both": "both",
    "client_or_server": "both",   # packwiz 对此发警告，统一按 both
    "singleplayer_only": "client",
    # "unknown" 是 Modrinth 给资源包/光影等无端侧概念的项目的取值，
    # packwiz 遇到不认识的 environment 会警告并保守按 both 处理。
    "unknown": "both",
}

# 需要人工留意的环境值：packwiz 也认为语义模糊
AMBIGUOUS_ENV = {"client_or_server", "unknown"}


def fetch_version(vid):
    url = f"{API}/version/{vid}"
    req = urllib.request.Request(url, headers={"User-Agent": pc.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def category_of(rel):
    if rel.startswith("resourcepacks/"):
        return "资源包"
    if rel.startswith("shaderpacks/"):
        return "光影"
    return "模组"


def check_one(item):
    rel, data = item
    name = data.get("name", rel)
    declared = data.get("side", "")
    problems, notes = [], []
    cat = category_of(rel)

    mr = (data.get("update") or {}).get("modrinth")
    mode = data.get("download", {}).get("mode", "")

    # --- 无 Modrinth 上游：无法自动复核 ---
    if not mr or not mr.get("mod-id"):
        if mode == "metadata:curseforge":
            notes.append("CurseForge 来源，需用 packwiz 复核 side")
        elif cat == "模组":
            notes.append("无 Modrinth 上游，side 需人工确认")
        return {"file": rel, "name": name, "declared": declared,
                "problems": problems, "notes": notes}

    vid = mr.get("version")
    if not vid:
        notes.append("元数据缺少 version，无法复核")
        return {"file": rel, "name": name, "declared": declared,
                "problems": problems, "notes": notes}

    ver = fetch_version(vid)
    if ver is None:
        notes.append(f"无法获取版本 {vid}（可能已被上游删除）")
        return {"file": rel, "name": name, "declared": declared,
                "problems": problems, "notes": notes}

    env = ver.get("environment")

    if env is None:
        # 资源包 / 光影通常没有 environment
        if cat in ("资源包", "光影"):
            # 这类文件由 packwiz 映射为 both（资源包在两端都需要）
            if declared not in ("both", ""):
                notes.append(
                    f"{cat}的 side 为 \"{declared}\"，通常应为 both"
                )
        else:
            notes.append("上游未提供 environment，保守按 both 处理")
        return {"file": rel, "name": name, "declared": declared,
                "env": env, "problems": problems, "notes": notes}

    exp = SIDE_MAP.get(env)
    if exp is None:
        problems.append(
            f"上游 environment=\"{env}\" 是未知值，"
            f"packwiz 与 packwiz_common 均无法解析"
        )
    elif exp != declared:
        problems.append(
            f"side=\"{declared}\" 与上游 environment=\"{env}\" 不符"
            f"（应为 \"{exp}\"）"
        )
    elif env in AMBIGUOUS_ENV:
        # 资源包 / 光影的 environment 恒为 unknown，这是正常取值，不提示。
        if cat == "模组":
            notes.append(
                f"上游 environment=\"{env}\" 无法确定端侧，"
                f"当前保守按 \"both\" 处理"
            )

    return {"file": rel, "name": name, "declared": declared,
            "env": env, "problems": problems, "notes": notes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", metavar="REL")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--prefix", default="mods/,resourcepacks/,shaderpacks/")
    ap.add_argument("--show-notes", action="store_true",
                    help="列出提示详情（默认只计数）")
    args = ap.parse_args()

    prefixes = tuple(p for p in args.prefix.split(",") if p)
    metas = pc.iter_meta(prefixes)
    if args.explain:
        metas = [m for m in metas if m[0] == args.explain]
        if not metas:
            print(f"! 找不到 {args.explain}")
            return 1

    if not args.explain:
        print("== check_side.py ==")
        print(f"  依据 Modrinth 版本的 environment 字段复核 {len(metas)} 个文件\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for r in ex.map(check_one, metas):
            results.append(r)

    if args.explain:
        for r in results:
            print(f"### {r['file']}  ({r['name']})")
            print(f"    .pw.toml side        = \"{r['declared']}\"")
            print(f"    上游 environment     = {r.get('env')!r}")
            if r.get("env") in SIDE_MAP:
                print(f"    按 packwiz 规则应为  = \"{SIDE_MAP[r['env']]}\"")
            for p in r["problems"]:
                print(f"    [不一致] {p}")
            for n in r["notes"]:
                print(f"    [提示] {n}")
            print()
        return 0

    bad = [r for r in results if r["problems"]]
    noted = [r for r in results if not r["problems"] and r["notes"]]

    if bad:
        print(f"[不一致] 需修正 —— {len(bad)} 个")
        for r in bad:
            print(f"  x {r['file']}  [{r['name']}]")
            for p in r["problems"]:
                print(f"      {p}")
        print()

    if noted:
        print(f"[提示] 需人工留意 —— {len(noted)} 个")
        if args.show_notes:
            for r in noted:
                print(f"  - {r['file']}  [{r['name']}]")
                for n in r["notes"]:
                    print(f"      {n}")
        else:
            from collections import Counter
            cat = Counter()
            for r in noted:
                for n in r["notes"]:
                    cat[n.split("，")[0]] += 1
            for k, v in cat.most_common():
                print(f"      {v:3d} 个：{k}")
            print("      （加 --show-notes 查看具体文件）")
        print()

    print(f"汇总: 复核 {len(results)} / 不一致 {len(bad)} / 提示 {len(noted)}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        print(f"  结果已写入 {args.json}")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
