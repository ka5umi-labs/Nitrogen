# 变更记录

本文件记录每个版本的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [未发布]

### 迁移到 packwiz

本版本起，Nitrogen 的开发流程从手工管理 jar 迁移到 packwiz：

- 模组以 `.pw.toml` 元数据形式管理，不再直接存放 jar
- 新增 `tools/` 校验脚本与 GitHub Actions CI
- 新增铁律扫描：自动检测会破坏"原版双向直连"的模组

### 从 7.3 mrpack 导入的现状

- 模组 108 个（102 个来自 Modrinth、2 个 CurseForge 独占、4 个无上游渠道）
- 资源包 7 个、光影 3 个
- `side` 字段：71 个 client、47 个 both

铁律扫描结果：**BLOCK 0**。3 个模组在 configuration 阶段注册通道，
经人工核实为配置同步用途，需在游戏内验证原版客户端可正常加入（见下）。

---

## [7.3] - 2026-10-09

- 支持 Minecraft 26.3、Fabric 0.19.5
- 初始 packwiz 化版本

## [7.2]

- 支持 Minecraft 26.2

---

## 待验证事项

以下事项 AI 已完成静态检查，但**需要作者在游戏内确认**：

- [ ] 包能正常启动
- [ ] `Open to LAN` 后原版客户端能加入（重点验证 configuration 阶段
      注册通道的三个模组：Eclipse's Tweakeroo Additions、
      SuperMartijn642's Config Lib、ViaFabricPlus）
- [ ] 能连上原版服务器
- [ ] 按键无冲突
- [ ] 光影可正常切换
- [ ] CozyUI+ 在 26.3 下显示正常（上游未标注支持 26.3）
