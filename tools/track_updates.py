#!/usr/bin/env python3
"""
track_updates.py —— 上游更新追踪 / 新版本升级助手

用途
================================================================
回答两个问题：

1. 目标 MC 版本下，还有哪些模组没跟上？ —— 决定"能不能发新版"。
2. 已装模组有哪些出了新版本？ —— 决定"要不要升级"。

对每个模组查询 Modrinth / CurseForge，判断其是否有支持目标 MC 版本
+fabric 的构建，并区分：

  可升级   —— 有新版本，且支持目标 MC 版本
  已最新   —— 当前就是最新
  未跟进   —— 上游尚无支持目标 MC 版本的构建（阻塞项，需等待或找替代）
  无上游   —— url 模式，无自动更新渠道（需手动处理）

用法
================================================================
    # 查看所有未跟进目标版本的模组（发新版前跑）
    python3 tools/track_updates.py --mc 26.3 --only-blocked

    # 全体更新检查
    python3 tools/track_updates.py

    # 同时检查不同 MC 版本，评估升级到新版本的可行性
    python3 tools/track_updates.py --mc 26.4 --only-blocked

    # 导出机器可读结果
    python3 tools/track_updates.py --json updates.json

退出码：0 正常；1 存在未跟进模组（--only-blocked 时也返回 0，避免误报 CI 失败）
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packwiz_common as pc  # noqa: E402

API = "https://api.modrinth.com/v2"


def api_get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": pc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:
            last = e
        import time
        time.sleep(1.5 * (i + 1))
    raise last


# 资源包 / 光影的 loader 与模组不同，不能按 fabric 过滤
PACK_LOADERS = ("minecraft", "iris", "vanilla", "canvas", "optifine")


def pick_best_version(versions, mc, loaders=("fabric", "quilt")):
    """从版本列表中挑出支持目标 MC 的最佳版本。

    对资源包 / 光影（loader 为 minecraft / iris 等）只要求 MC 版本匹配。
    """
    ok = []
    for v in versions:
        if mc not in v.get("game_versions", []):
            continue
        v_loaders = v.get("loaders") or []
        # 无 loader 信息，或含资源包类 loader —— 视为匹配
        if v_loaders and not any(
            l in v_loaders for l in loaders + PACK_LOADERS
        ):
            continue
        ok.append(v)
    if not ok:
        return None
    releases = [v for v in ok if v.get("version_type") == "release"]
    pool = releases or ok
    pool.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    return pool[0]


def primary_file(version):
    files = version.get("files") or []
    for f in files:
        if f.get("primary"):
            return f
    return files[0] if files else None


def check_one(item, mc):
    rel, data = item
    name = data.get("name", rel)
    upd = data.get("update", {})
    dl = data.get("download", {})
    mode = dl.get("mode", "")

    # CurseForge 模组：Modrinth 查不到，单独标注
    if "curseforge" in upd or mode == "metadata:curseforge":
        return {
            "file": rel, "name": name, "source": "curseforge",
            "status": "manual-check",
            "note": "CurseForge 来源，请用 packwiz update 检查",
            "current": dl.get("url", "").rsplit("/", 1)[-1],
        }

    mr = upd.get("modrinth")
    if not mr or not mr.get("mod-id"):
        return {
            "file": rel, "name": name, "source": "url",
            "status": "no-upstream",
            "note": "无自动更新渠道，需手动替换 jar",
            "current": data.get("filename", ""),
        }

    pid = mr["mod-id"]
    cur_vid = mr.get("version")
    try:
        versions = api_get(f"{API}/project/{pid}/version")
    except Exception as e:
        return {"file": rel, "name": name, "source": "modrinth",
                "status": "error", "note": f"查询失败: {e}"}

    if not versions:
        return {"file": rel, "name": name, "source": "modrinth",
                "status": "error", "note": "上游无任何版本"}

    cur = next((v for v in versions if v["id"] == cur_vid), None)
    best = pick_best_version(versions, mc)
    latest_overall = None
    for v in versions:
        if latest_overall is None or \
           v.get("date_published", "") > latest_overall.get("date_published", ""):
            latest_overall = v

    if best is None:
        cat = ("资源包" if rel.startswith("resourcepacks/")
               else "光影" if rel.startswith("shaderpacks/") else "模组")
        note = f"上游尚无支持 MC {mc} 的构建"
        if cat != "模组":
            note += (f"（{cat}，上游通常不逐版本标注，"
                     f"实际多半仍可用，不构成发版阻塞）")
        return {
            "file": rel, "name": name, "source": "modrinth",
            "category": cat,
            "status": "not-followed",
            "note": note,
            "current": cur.get("version_number") if cur else "?",
            "latest_overall": latest_overall.get("version_number"),
            "latest_overall_mc": latest_overall.get("game_versions", [])[-3:],
        }

    if cur_vid and best["id"] == cur_vid:
        return {
            "file": rel, "name": name, "source": "modrinth",
            "status": "up-to-date",
            "current": best.get("version_number"),
        }

    return {
        "file": rel, "name": name, "source": "modrinth",
        "status": "updatable",
        "current": cur.get("version_number") if cur else "?",
        "available": best.get("version_number"),
        "available_id": best["id"],
        "game_versions": best.get("game_versions", []),
    }


STATUS_ORDER = {
    "not-followed": 0,   # 阻塞发版，最重要
    "updatable": 1,
    "manual-check": 2,
    "no-upstream": 3,
    "error": 4,
    "up-to-date": 5,
}

STATUS_LABEL = {
    "not-followed": "未跟进",
    "updatable": "可升级",
    "manual-check": "手动确认",
    "no-upstream": "无上游",
    "error": "查询失败",
    "up-to-date": "已最新",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", default=None,
                    help="目标 MC 版本；默认读 pack.toml")
    ap.add_argument("--only-blocked", action="store_true",
                    help="只列出未跟进的模组")
    ap.add_argument("--only-updatable", action="store_true",
                    help="只列出可升级的模组")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--prefix", default="mods/,resourcepacks/,shaderpacks/")
    args = ap.parse_args()

    mc = args.mc
    if not mc:
        pack = os.path.join(pc.ROOT, "pack.toml")
        m = re.search(r'^minecraft = "([^"]+)"', open(pack, encoding="utf-8").read(),
                      re.M)
        if not m:
            print("! 无法从 pack.toml 读取 minecraft 版本，请用 --mc 指定")
            return 1
        mc = m.group(1)

    prefixes = tuple(p for p in args.prefix.split(",") if p)
    metas = pc.iter_meta(prefixes)

    print("== track_updates.py ==")
    print(f"  目标 MC 版本: {mc}")
    print(f"  检查 {len(metas)} 个文件（并发 {args.jobs}）\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(check_one, m, mc): m for m in metas}
        done = 0
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
            done += 1
            if done % 20 == 0:
                print(f"  ...{done}/{len(metas)}")

    results.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9),
                                r["name"].lower()))

    if args.only_blocked:
        show = [r for r in results if r["status"] == "not-followed"]
    elif args.only_updatable:
        show = [r for r in results if r["status"] in
                ("updatable", "not-followed")]
    else:
        show = results

    from collections import Counter
    counts = Counter(r["status"] for r in results)

    print()
    cur_status = None
    for r in show:
        if r["status"] != cur_status:
            cur_status = r["status"]
            print(f"--- {STATUS_LABEL[cur_status]} ---")
        if r["status"] == "not-followed":
            print(f"  {r['name']}")
            print(f"      当前 {r.get('current')} | 上游最新 "
                  f"{r.get('latest_overall')} (MC {r.get('latest_overall_mc')})")
        elif r["status"] == "updatable":
            print(f"  {r['name']}: {r.get('current')} -> {r.get('available')}")
        else:
            print(f"  {r['name']}: {r.get('note') or r.get('current') or ''}")

    print()
    print("汇总: " + " / ".join(
        f"{STATUS_LABEL[k]} {v}" for k, v in
        sorted(counts.items(), key=lambda x: STATUS_ORDER.get(x[0], 9))))

    blocked = counts.get("not-followed", 0)
    if blocked:
        print()
        print(f"注意: {blocked} 个模组尚未支持 MC {mc}。")
        print("      这些是升级到该版本的主要阻塞项，需等待上游更新或寻找替代方案。")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"mc": mc, "results": results}, fh,
                      ensure_ascii=False, indent=2)
        print(f"\n  结果已写入 {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
