# 日常开发流程

本文档描述 Nitrogen 整合包的日常工作流。约束与边界见 [AGENTS.md](../AGENTS.md)。

## 环境准备

```bash
# packwiz 已放在仓库根目录（不入 git）
./packwiz.exe --version

# 校验脚本需要 Python 3.8+
python3 --version
```

## 一、新增模组

### 1. 先查铁律

**不要直接 add。** 先确认模组是否违反"原版双向直连"：

```bash
# 用 Modrinth 搜索看项目页的 client/server side
# 若项目页写着 server_side: required 或必需服务端组件，直接排除

# 加入后立刻扫描
./packwiz.exe mr add <slug>
./packwiz.exe refresh
python3 tools/scan_channels.py --explain mods/<slug>.pw.toml
```

判定标准：

- 出现 `[BLOCK]` → 立即回滚，该模组不可用
- 出现 `configuration 阶段` 标记 → 需作者在游戏内验证原版客户端能否加入
- 只有 `[INFO]` → 可以加入

### 2. 加入并提交

```bash
./packwiz.exe mr add <slug>        # Modrinth 来源
./packwiz.exe cf add <slug>        # CurseForge 来源
./packwiz.exe refresh

python3 tools/verify_pack.py
python3 tools/check_side.py --explain mods/<slug>.pw.toml

git add -A
git commit -m "feat(mods): 新增 <模组名>"
```

### 3. 依赖检查

很多模组需要前置（Fabric API、Cloth Config、YACL 等）。packwiz 不会自动装前置：

```bash
python3 tools/track_updates.py --only-blocked   # 顺带看是否有奇怪状态
./packwiz.exe mr add <前置的 slug>
```

## 二、删除模组

```bash
./packwiz.exe remove <name>
./packwiz.exe refresh
python3 tools/verify_pack.py
git commit -am "fix(mods): 移除 <模组名>"
```

**删除前必须确认**：该模组是不是别的前置？删除后用
`python3 tools/verify_pack.py --online` 确认没有断链。

## 三、升级模组

### 查看可升级项

```bash
python3 tools/track_updates.py
```

输出分五类：**未跟进**（上游没出目标 MC 版本）、**可升级**、
**手动确认**（CurseForge 来源）、**无上游**（url 模式）、**已最新**。

### 批量升级

```bash
# 先干跑看结果
./packwiz.exe update --all --dry-run

# 实际升级
./packwiz.exe update --all
./packwiz.exe refresh

python3 tools/verify_pack.py
git commit -am "chore(mods): 批量升级至最新版本"
```

### 单个升级

```bash
./packwiz.exe update <name>
./packwiz.exe refresh
git commit -am "chore(mods): 升级 <模组名>"
```

### 升级后必做

1. `python3 tools/scan_channels.py --changed-only`
   —— 确认新版本没有引入网络通道
2. 检查 `git diff` —— 升级常会带来 `side` 字段变化
3. **作者在游戏中测试**（AI 不做这一步）

## 四、修改配置 / 覆盖文件

`overrides/` 下的文件会覆盖到玩家实例。改动后：

```bash
./packwiz.exe refresh
python3 tools/verify_pack.py
git commit -am "chore(overrides): 调整 <配置项>"
```

## 五、修复 bug

```bash
git checkout -b fix/<简述>
# 修改
./packwiz.exe refresh
python3 tools/verify_pack.py
git commit -am "fix(...): <描述>"
```

## 六、发版前检查清单

```bash
# 1. 全量校验
python3 tools/verify_pack.py --online

# 2. 铁律扫描（必须 BLOCK 0）
python3 tools/scan_channels.py

# 3. side 复核（必须不一致 0）
python3 tools/check_side.py

# 4. 看还有哪些模组没跟上
python3 tools/track_updates.py --only-blocked
```

四项全过之后才进入 [发版流程](release.md)。

## 七、AI 协作方式

让 AI 帮你做事时，有效的指令形态：

```
读取 mods/ 下所有元数据，找出所有 side="both" 但实际是纯客户端的模组，
用 tools/check_side.py 复核，列出需要修正的清单和对应的 .pw.toml 改动。
```

```
运行 tools/track_updates.py，把"未跟进"的模组逐个查 Modrinth，
判断是作者弃更还是有替代方案，给出结论表格。
```

不有效的指令形态：

```
帮我优化整合包          # 太模糊，无法验证
把这些模组都升级了      # 涉及铁律风险，需要先扫描
```

**记住**：AI 不会替你进游戏测试。任何"性能变好了""没有崩溃"的说法都必须由你在游戏中确认。
