# MC 大版本升级应对清单

每当 Minecraft 发布新版本，按本文档逐项推进。目标是**尽快出可用包**，
且不破坏铁律。

## 阶段一：确认上游基础（版本发布后 0-3 天）

```bash
# 1. 查 Fabric loader 是否支持新版本
#    https://fabricmc.net/develop/

# 2. 查核心模组是否跟进 —— 这些是硬阻塞
./packwiz.exe mr add fabric-api        # 看是否能选到新版本
```

**硬阻塞模组**（缺任何一个都不要发版）：

| 模组 | 作用 | 缺失后果 |
|---|---|---|
| Fabric API | 几乎所有 Fabric 模组的前置 | 大面积失效 |
| Fabric Loader | 加载器本体 | 无法启动 |
| Sodium | 渲染优化 | 性能回退到原版水平 |
| Lithium | 服务端逻辑优化 | 性能回退 |
| Mod Menu | 模组管理界面 | 用户无法配置 |

**软阻塞模组**（可延后，但要记录）：

Iris（光影）、资源包、装饰性模组、小众工具模组。

## 阶段二：批量评估（版本发布后 3-7 天）

```bash
# 改 pack.toml 到新 MC 版本，然后看整体跟进情况
python3 tools/track_updates.py --mc <新版本>
```

把结果分三类：

1. **已跟进** —— 可直接升级
2. **未跟进但非核心** —— 记录在 CHANGELOG 的"已知问题"
3. **未跟进且是核心** —— 停止流程，等待

对于第 3 类，逐个去模组的 GitHub / Discord 确认作者是否有计划。
如果作者已弃更，需要找替代方案（见下一节）。

## 阶段三：升级与验证

```bash
./packwiz.exe update --all --dry-run
./packwiz.exe update --all
./packwiz.exe refresh

python3 tools/verify_pack.py --online
python3 tools/scan_channels.py
python3 tools/check_side.py
python3 tools/check_bundled.py
```

**打包分发的模组不会被自动升级。** 每次 MC 大版本升级时，这些模组
（`mods/` 下的 jar）都需要单独找支持新版本的构建 —— 见
[bundled-mods.md](bundled-mods.md)。它们通常是升级路上的主要阻塞项，
因为上游往往没有公开 release。

然后交给作者做游戏内测试。

## 阶段四：补齐缺口

新 MC 版本往往带来**新的优化机会**。此时是加入新模组的最佳时机：

```bash
# 去 Modrinth 找支持新版本的新模组
# 分类浏览：optimization / lightweight
```

加入前必须过铁律扫描。新模组常见坑：

- 一些"优化"模组会注册自定义通道做客户端-服务端同步 → 需 REVIEW
- 一些模组标称 client 但要求服务端装配套模组 → 直接排除

## 找替代方案

当核心模组弃更时：

1. 查 Modrinth 上的 fork / 移植版（搜 `<模组名> port` / `<模组名> updated`）
2. 查该模组的功能是否已被其他活跃模组覆盖
3. 若替代品质量不足，考虑暂时不用（宁可少一个优化，不引入风险）

替代品必须重新过铁律扫描。

## 版本跨越特别提示

从 1.21.x 跳到 26.x 这类**大跨越**时：

- Mojang 改了版本号方案，很多模组的 `game_versions` 标注会混乱
- Modrinth 上可能出现"标注 1.21.11 但实际支持 26.x"的情况
- 用 `./packwiz.exe mr add <slug> --version-id <id>` 可以指定具体版本

## 记录

每次 MC 升级都应在 `docs/decisions/` 下留一份记录，写明：

- 升级日期与版本
- 各模组的跟进时间
- 遇到的阻塞与解决方式
- 新增/移除的模组及原因

这样下次升级能参考上次的经验。
