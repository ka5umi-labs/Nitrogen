# 无上游分发渠道的模组

这些模组的 jar 既不在 Modrinth 也不在 CurseForge 上，packwiz 无法自动
获取与更新。它们的 `.pw.toml` 使用 `url` 模式，URL 指向**本仓库的
GitHub Release**。

## 为什么不能用 Modrinth/CurseForge

已实测核实（用 sha1 比对，全部 404 或无对应文件）：

| 模组 | 情况 |
|---|---|
| MasaGadget | 作者只发 1.19.4 及以前；26.x 构建由第三方 fork 产出 |
| Modern UI (Unofficial Port) | 官方 ModernUI 停留在 3.13.0；26.3 版是非官方移植 |
| Oh My Minecraft Client | 官方最新 release 是 2022 年的 0.5 |
| Eating Animation Fork | 26.3 构建只在 fork 仓库，且已删除对应 release |

## 处理机制

这些模组的 `.pw.toml` 形如：

```toml
name = "MasaGadget"
filename = "MasaGadget-mc26.3-fabric-4.0.403-development.jar"
side = "client"

[download]
url = "https://github.com/ka5umi-labs/Nitrogen/releases/download/v7.3/MasaGadget-mc26.3-fabric-4.0.403-development.jar"
hash-format = "sha512"
hash = "..."
```

**没有 `[update]` 段落** —— `packwiz update --all` 会跳过它们。

## 发版时必须做的事

每次发版，必须把这 4 个 jar 上传到对应版本的 GitHub Release：

```
Release tag: v<版本号>
```

上传的文件名必须与 `.pw.toml` 中的 `filename` 字段**完全一致**，
否则玩家端 packwiz 会下载失败。

上传后验证：

```bash
python3 tools/verify_pack.py --online
```

## 更新这些模组

没有自动流程，步骤是：

1. 找到新版 jar（去上游 fork 仓库 / 作者群 / 自行构建）
2. 在 Modrinth 上按 sha1 确认它确实不在官方渠道
3. 计算新哈希：

```bash
python3 -c "
import hashlib,sys
p=sys.argv[1]
print('sha512:',hashlib.sha512(open(p,'rb').read()).hexdigest())
" new-jar.jar
```

4. 更新 `.pw.toml` 的 `filename`、`url`、`hash` 三个字段
5. 把新 jar 上传到 GitHub Release
6. `./packwiz.exe refresh && python3 tools/verify_pack.py`

## 长期方案

这些模组是维护负担。建议留意：

- 是否有官方或更活跃的替代品出现
- 是否可以自行维护一个公开仓库/Release 来托管这些构建
- 是否值得向上游提交 PR 让官方支持新版本

若某个模组长期无人维护且影响升级，应考虑移除。

## 当前清单（7.3）

| 模组 | 文件 | 上游 |
|---|---|---|
| MasaGadget | `MasaGadget-mc26.3-fabric-4.0.403-development.jar` | plusls/MasaGadget 的第三方 26.x fork |
| Modern UI (Unofficial Port) | `ModernUI-Fabric-26.3-3.14.7-universal.jar` | Huziyang520/ModernUI-Unofficial-Port |
| Oh My Minecraft Client | `Oh-My-Minecraft-Client-v0.7.1-mc26.3-fabric.jar` | plusls/oh-my-minecraft-client 的 26.x fork |
| Eating Animation Fork | `eating-animation-fork-26.3+5.1.0.jar` | Fring-BS/Eating-Animation-Fork |

另有 2 个 **CurseForge 独占**模组（有 `[update.curseforge]`，能自动更新）：

| 模组 | CurseForge 项目 | 已核实 |
|---|---|---|
| Connectivity | 470193 | 文件 9011123，sha1 与包内一致 |
| Cupboard | 326652 | 文件 8890593，sha1 与包内一致 |
