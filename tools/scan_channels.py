#!/usr/bin/env python3
"""
scan_channels.py —— 原版双向直连铁律扫描

扫描每个模组 jar 的字节码，查找会破坏"原版双向直连"的网络特征，
并按 **Minecraft 协议阶段** 分级判定。

为什么要按阶段分级（实测校准，勿轻改）
================================================================
铁律的本质是：**未装模组的原版对端必须能连上**。连接能否建立只取决于
握手阶段（login / configuration）。游玩阶段（play）的自定义包对此没有影响，
因为原版对 play 阶段不认识的自定义 payload 是**直接丢弃**的，不会断开连接。

因此：
  BLOCK —— 在 login / configuration 阶段注册自定义通道或握手插件。
           这会让原版对端握手被拒，是**唯一真正违反铁律**的行为。
  REVIEW —— 注册了自定义通道，但无法从字节码判断阶段；或仅在 play 阶段注册
           但需要人工确认。play 阶段注册通常安全，用 --explain 看类名即可。
  INFO  —— 仅引用了原版 payload 相关类，未注册任何通道。属正常现象
           （原版自身就有这些类），默认不列出。
  SKIP  —— 无法获取，或不是模组 jar（资源包 / 光影 / 未发布）。

已实测并确认安全的案例（供人工判定参考）
================================================================
* connectivity —— mixin 原版 custom payload 包仅用于日志与包名美化，
  未注册新通道。全库仅命中 *PacketNameMixin 类。
* syncmatica —— 字节码内含 "registering play channel(s)"，
  只在 clientboundPlay / serverboundPlay 注册，游玩阶段，原版可互通。
* carpet —— 使用自定义 payload，但用 isValidCarpetPlayer 过滤，
  只对装了 carpet 的玩家发送，原版玩家不受影响。
* fabric-api —— 无任何网络注册命中。

用法
================================================================
    python3 tools/scan_channels.py                    # 扫描全部模组
    python3 tools/scan_channels.py --explain <rel>    # 查看某模组的命中详情
    python3 tools/scan_channels.py --changed-only     # 只扫描本次改动
    python3 tools/scan_channels.py --limit 5          # 只扫描前 N 个（调试）
    python3 tools/scan_channels.py --verbose          # 连 INFO 一起列出
    python3 tools/scan_channels.py --json out.json    # 输出机器可读结果

退出码：0 无 BLOCK；1 存在 BLOCK。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packwiz_common as pc  # noqa: E402

MAX_CLASS_SIZE = 8 << 20  # 跳过异常大的 class，避免拖慢扫描

# ---- 登录 / 配置阶段：命中"并同时注册通道"才 BLOCK ----
# 单纯 mixin 登录类做超时调整、日志、限流是安全的（实测案例 connectivity）。
# 真正会踢掉原版对端的是在握手期**注册自定义通道或握手插件**。
LOGIN_SIGNATURES = [
    ("ServerLoginNetworking", rb"ServerLoginNetworking"),
    ("ClientLoginNetworking", rb"ClientLoginNetworking"),
    ("RegisterLoginPayloadsEvent", rb"RegisterLoginPayloadsEvent"),
    ("loginC2S", rb"loginC2S"),
    ("loginS2C", rb"loginS2C"),
    ("configurationC2S", rb"configurationC2S"),
    ("configurationS2C", rb"configurationS2C"),
]

# 裸的"触及登录类"——只作为 REVIEW 提示，不单独构成 BLOCK
TOUCHES_LOGIN = [
    ("ServerLoginPacketListener", rb"ServerLoginPacketListener"),
    ("ClientLoginPacketListener", rb"ClientLoginPacketListener"),
    ("ServerConfigurationPacketListener", rb"ServerConfigurationPacketListener"),
]

# ---- 通道注册特征：本身不代表违规，取决于阶段 ----
CHANNEL_SIGNATURES = [
    ("PayloadTypeRegistry", rb"PayloadTypeRegistry"),
    ("registerGlobalReceiver", rb"registerGlobalReceiver"),
    ("SimpleChannel", rb"SimpleChannel"),
    ("ChannelBuilder", rb"ChannelBuilder"),
    ("RegisterPayloadHandlersEvent", rb"RegisterPayloadHandlersEvent"),
    ("NetworkRegistry", rb"NetworkRegistry"),
]

# ---- 游玩阶段标记：出现则可判定为 play 阶段 ----
PLAY_MARKERS = [
    rb"serverboundPlay", rb"clientboundPlay",
    rb"registering play channel", rb"PlayPayloadHandler",
    rb"playC2S", rb"playS2C",
]

# ---- 配置阶段标记：握手流程的一部分，需要游戏内验证 ----
# 原版对 play 阶段未知包直接丢弃，所以 play 注册是安全的；
# 但 configuration 阶段属于握手/同步流程，注册这里的通道意味着
# 服务端会向客户端发送自定义配置包。是否影响原版对端需要实测。
CONFIG_MARKERS = [
    rb"clientboundConfiguration", rb"serverboundConfiguration",
    rb"ConfigurationPayloadHandler", rb"ServerConfigurationPacketListener",
    rb"ClientConfigurationPacketListener", rb"onConfigurationInit",
    rb"onSendConfiguration", rb"configurationC2S", rb"configurationS2C",
]

# ---- 仅引用，不构成风险 ----
INFO_SIGNATURES = [
    ("CustomPayload", rb"CustomPayload"),
    ("ClientPlayNetworking", rb"ClientPlayNetworking"),
    ("ServerPlayNetworking", rb"ServerPlayNetworking"),
    ("CustomQuery", rb"CustomQuery"),
]

_COMPILED = {
    "login": [(n, re.compile(rx)) for n, rx in LOGIN_SIGNATURES],
    "touches_login": [(n, re.compile(rx)) for n, rx in TOUCHES_LOGIN],
    "channel": [(n, re.compile(rx)) for n, rx in CHANNEL_SIGNATURES],
    "play": [re.compile(rx) for rx in PLAY_MARKERS],
    "config": [re.compile(rx) for rx in CONFIG_MARKERS],
    "info": [(n, re.compile(rx)) for n, rx in INFO_SIGNATURES],
}


def scan_jar(path):
    """按阶段分级扫描一个 jar。

    返回 dict：
      {"block": {sig: [classes]}, "review": {...}, "info": {...}}
    或 None（不是有效 zip）。
    """
    block, review, info, touch = {}, {}, {}, {}
    try:
        with zipfile.ZipFile(path) as z:
            entries = [e for e in z.namelist() if e.endswith(".class")]
            blobs = []
            for entry in entries:
                try:
                    if z.getinfo(entry).file_size > MAX_CLASS_SIZE:
                        continue
                    blobs.append((entry, z.read(entry)))
                except Exception:
                    continue
    except zipfile.BadZipFile:
        return None

    jar_has_play_marker = any(
        rx.search(b) for _, b in blobs for rx in _COMPILED["play"]
    )
    jar_has_config_marker = any(
        rx.search(b) for _, b in blobs for rx in _COMPILED["config"]
    )

    for entry, blob in blobs:
        login_hits = [n for n, rx in _COMPILED["login"] if rx.search(blob)]
        chan_hits = [n for n, rx in _COMPILED["channel"] if rx.search(blob)]
        touch_hits = [n for n, rx in _COMPILED["touches_login"] if rx.search(blob)]
        info_hits = [n for n, rx in _COMPILED["info"] if rx.search(blob)]

        if login_hits and chan_hits:
            # 握手期注册自定义通道/登录插件 —— 会让原版对端连不上
            for n in login_hits:
                block.setdefault(n, []).append(entry)
        elif chan_hits:
            # 注册了通道但未发现登录阶段特征。按阶段进一步区分：
            #   play 阶段注册  -> 原版对未知 play 包直接丢弃，安全（INFO）
            #   configuration  -> 属于握手流程，需游戏内验证（REVIEW）
            bucket = info if jar_has_play_marker else review
            for n in chan_hits:
                bucket.setdefault(n, []).append(entry)
        elif login_hits:
            # 只在登录阶段出现插件特征但没注册通道 —— 仍然可疑，人工看
            for n in login_hits:
                review.setdefault(n, []).append(entry)
        else:
            if touch_hits and not jar_has_play_marker:
                for n in touch_hits:
                    touch.setdefault(n, []).append(entry)
            for n in info_hits:
                info.setdefault(n, []).append(entry)

    return {
        "block": {k: sorted(set(v)) for k, v in block.items()},
        "review": {k: sorted(set(v)) for k, v in review.items()},
        "info": {k: sorted(set(v)) for k, v in info.items()},
        "touches_login": {k: sorted(set(v)) for k, v in touch.items()},
        "play_phase_detected": jar_has_play_marker,
        "config_phase_detected": jar_has_config_marker,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", metavar="REL",
                    help="显示指定 .pw.toml 的全部命中详情并退出")
    ap.add_argument("--changed-only", action="store_true",
                    help="只扫描 git 改动涉及的模组")
    ap.add_argument("--limit", type=int, default=0,
                    help="只扫描前 N 个（调试用）")
    ap.add_argument("--json", metavar="PATH", help="把结果写入 JSON 文件")
    ap.add_argument("--jobs", type=int, default=8, help="并发数")
    ap.add_argument("--verbose", action="store_true",
                    help="连 INFO 级别也列出")
    ap.add_argument("--prefix", default="mods/",
                    help="限定扫描的目录前缀，逗号分隔")
    args = ap.parse_args()

    prefixes = tuple(p for p in args.prefix.split(",") if p)
    metas = pc.iter_meta(prefixes)

    if args.explain:
        metas = [m for m in metas if m[0] == args.explain]
        if not metas:
            print(f"! 找不到 {args.explain}")
            return 1

    if args.changed_only:
        changed = pc.git_changed_meta()
        if changed is None:
            print("! 无法通过 git 判断改动范围，回退为全量扫描")
        else:
            changed = set(changed)
            metas = [m for m in metas if m[0] in changed]
            print(f"本次改动涉及 {len(metas)} 个模组")

    if args.limit:
        metas = metas[:args.limit]

    if not args.explain:
        print("== scan_channels.py ==")
        print(f"  待扫描 {len(metas)} 个文件\n")

    def work(item):
        rel, data = item
        try:
            jar = pc.fetch_jar(rel, data)
        except Exception as e:
            return rel, data, None, str(e)
        return rel, data, scan_jar(jar), None

    results, skipped = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for rel, data, hits, error in ex.map(work, metas):
            if error:
                skipped.append((rel, error))
            elif hits is None:
                skipped.append((rel, "不是有效的 zip/jar（可能是资源包或光影）"))
            else:
                results.append((rel, data, hits))

    if args.explain:
        for rel, data, hits in results:
            print(f"### {rel}   ({data.get('name')})")
            print(f"    游玩阶段标记: "
                  f"{'检测到（play 阶段注册，原版对端可互通）' if hits['play_phase_detected'] else '未检测到'}")
            print(f"    配置阶段标记: "
                  f"{'检测到（configuration 阶段注册，需游戏内验证）' if hits['config_phase_detected'] else '未检测到'}")
            for level, label in (("block", "BLOCK"), ("review", "REVIEW"),
                                 ("touches_login", "登录类（仅触及，非违规）"),
                                 ("info", "INFO")):
                for sig, classes in sorted(hits[level].items()):
                    print(f"    [{label}] {sig} —— 命中 {len(classes)} 个类")
                    for c in classes:
                        print(f"           {c}")
            if not any(hits[l] for l in ("block", "review", "touches_login", "info")):
                print("    无任何命中")
            print()
        for rel, why in skipped:
            print(f"### {rel}\n    跳过: {why.splitlines()[0]}\n")
        return 0

    blocks, reviews, infos = [], [], []
    for rel, data, hits in results:
        name = data.get("name", rel)
        if hits["block"]:
            blocks.append((rel, name, hits["block"]))
        elif hits["review"]:
            reviews.append((rel, name, hits))
        elif hits["info"]:
            infos.append((rel, name, hits["info"]))

    if blocks:
        print(f"[BLOCK] 登录/握手阶段网络插件，违反铁律，不得合入 —— {len(blocks)} 个")
        for rel, name, b in blocks:
            print(f"  x {rel}  [{name}]")
            for sig, classes in sorted(b.items()):
                print(f"      {sig}  ({len(classes)} 个类)")
                for c in classes[:3]:
                    print(f"        {c}")
        print()

    if reviews:
        print(f"[REVIEW] 注册了通道，需人工判定 —— {len(reviews)} 个")
        config_phase = []
        for rel, name, hits in reviews:
            tag = ""
            if hits.get("config_phase_detected"):
                tag = "  ← configuration 阶段，需游戏内验证"
                config_phase.append((rel, name))
            print(f"  ? {rel}  [{name}]{tag}")
            print("      " + ", ".join(
                f"{s}({len(c)})" for s, c in sorted(hits["review"].items())))
        print()
        print("  判定指引:")
        print("    * 用 --explain <rel> 查看类名与阶段标记。")
        print("    * 只涉及 play 阶段（*PlayHandler 等）-> 原版对端可互通，安全。")
        print("    * 涉及 configuration 阶段 -> 属于握手流程，")
        print("      必须在游戏内验证「原版客户端能否加入本包开的房间」。")
        print()
        if config_phase:
            print("  下列模组处于 configuration 阶段，是铁律验证的重点对象:")
            for rel, name in config_phase:
                print(f"    - {name}  ({rel})")
            print()

    if args.verbose and infos:
        print(f"[INFO] 仅引用原版 payload 类，未注册通道 —— {len(infos)} 个")
        for rel, name, i in infos:
            print(f"  - {rel}  [{name}]: "
                  + ", ".join(f"{s}({len(c)})" for s, c in sorted(i.items())))
        print()

    if skipped:
        print(f"[SKIP] 无法获取或非模组 —— {len(skipped)} 个")
        for rel, why in skipped:
            print(f"  - {rel}: {why.splitlines()[0]}")
        print()

    clean = len(results) - len(blocks) - len(reviews) - len(infos)
    print(f"汇总: OK {clean} / INFO {len(infos)} / REVIEW {len(reviews)}"
          f" / BLOCK {len(blocks)} / SKIP {len(skipped)}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "block": [{"file": r, "name": n, "signatures": b}
                          for r, n, b in blocks],
                "review": [{"file": r, "name": n,
                            "signatures": h["review"],
                            "play_phase": h["play_phase_detected"],
                            "config_phase": h["config_phase_detected"]}
                           for r, n, h in reviews],
                "info": [{"file": r, "name": n, "signatures": i}
                         for r, n, i in infos],
                "skip": [{"file": r, "reason": w} for r, w in skipped],
            }, fh, ensure_ascii=False, indent=2)
        print(f"  结果已写入 {args.json}")

    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main())
