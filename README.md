# Nitrogen

基于 Fabric 的原版优化整合包。在不改变原版玩法内容的前提下，改善性能、界面手感与联机体验。

Modrinth: https://modrinth.com/modpack/nitrogen7

## 核心特性

**双向原版兼容** —— 这是本整合包最重要的约束：

1. 装本包后，可以直连**任意原版/纯净服务端**
2. 用本包作为房主联机（`Open to LAN`）时，**未装任何模组的原版玩家**能正常加入

这意味着包内不允许出现任何会注册自定义网络通道、改变握手协议或要求对端安装的模组。
详见 [AGENTS.md](AGENTS.md) 的铁律章节。

## 仓库结构

```
pack.toml           整合包元数据（版本、MC/Fabric 版本）
index.toml          文件索引（哈希清单，由 packwiz 生成）
mods/               模组：Modrinth 来源为 .pw.toml，非 Modrinth 来源为 jar
resourcepacks/      资源包元数据
shaderpacks/        光影元数据
overrides/          分发给玩家的覆盖文件（配置等）
bundled-mods.toml   打包分发模组的来源登记
tools/              校验脚本
docs/               开发文档
```

**分发模型**：Modrinth 只接受 `cdn.modrinth.com` 的下载链接，因此
不在 Modrinth 上的模组（CurseForge、无公开 release 的 fork 构建）
必须把 jar 直接放在 `mods/` 下，packwiz 会在 `mr export` 时自动打包进
`overrides/`。**不要把 jar 放进 `overrides/`** —— 会导出成
`overrides/overrides/`，玩家装了不生效。详见
[docs/bundled-mods.md](docs/bundled-mods.md)。

## 使用（玩家）

在本站下载 `.mrpack` 后，用以下启动器安装：

- [Prism Launcher](https://prismlauncher.org/)（推荐）
- [ATLauncher](https://atlauncher.com/about)
- [MultiMC](https://multimc.org/)

## 开发

### 需要的工具

- [packwiz](https://github.com/packwiz/packwiz) —— 放在仓库根目录命名为 `packwiz.exe`
- Python 3.8+（跑校验脚本）

### 快速开始

```bash
# 校验当前状态
python3 tools/verify_pack.py

# 铁律扫描（原版直连兼容性）
python3 tools/scan_channels.py

# 看哪些模组能升级 / 有哪些没跟上
python3 tools/track_updates.py
```

### 常用 packwiz 命令

```bash
./packwiz.exe mr add <slug>     # 从 Modrinth 新增模组
./packwiz.exe cf add <slug>     # 从 CurseForge 新增模组
./packwiz.exe remove <name>     # 删除模组
./packwiz.exe refresh           # 同步索引（任何改动后必须执行）
./packwiz.exe update --all      # 批量升级
./packwiz.exe mr export         # 导出整合包
```

### 文档

| 文档 | 内容 |
|---|---|
| [AGENTS.md](AGENTS.md) | **约束与边界，改动前必读** |
| [docs/workflow.md](docs/workflow.md) | 日常开发流程 |
| [docs/release.md](docs/release.md) | 发版流程 |
| [docs/mc-upgrade.md](docs/mc-upgrade.md) | MC 大版本升级清单 |
| [docs/bundled-mods.md](docs/bundled-mods.md) | 打包分发模组的维护 |

## 校验脚本

| 脚本 | 作用 |
|---|---|
| `tools/verify_pack.py` | 哈希/索引一致性 + 下载可达性 |
| `tools/scan_channels.py` | **铁律扫描**：检测网络通道注册与握手插件 |
| `tools/check_side.py` | 复核 `side` 字段与上游 `environment` 是否一致 |
| `tools/check_bundled.py` | 打包分发模组的登记、布局与许可证检查 |
| `tools/track_updates.py` | 上游更新追踪，找出未跟进新 MC 版本的模组 |

CI 会在每次 push 与 PR 时自动运行前四个。

## 贡献

欢迎提交建议与 bug 报告。提交模组建议时请说明：

- 模组用途
- 是否会在服务端也安装（即是否可能影响原版对端）

## 许可

见 [LICENSE](LICENSE)。整合包本身可自由分发（需标明作者、不得修改），
各模组版权归各自作者所有。
