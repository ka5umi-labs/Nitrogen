# AGENTS.md — Nitrogen 整合包开发约束

本文件是 AI 协作者（以及未来的你自己）在本仓库工作时的**最高约束**。
任何与本文冲突的操作建议，一律以本文为准。

---

## 1. 项目目标

Nitrogen 是一个 **Fabric 原版优化整合包**：在不改变原版玩法内容的前提下，改善性能、界面手感与联机体验。

成功的标准不是"模组越多越好"，而是同时满足：

1. **能进任何原版服务器** —— 玩家装本包后，可直连任意原版 / 纯净服务端。
2. **能被任何原版玩家进入** —— 玩家用本包作为房主 `Open to LAN` 或开服时，未装任何模组的原版玩家必须能正常加入。
3. **快速跟上 MC 新版本** —— 新版本发布后，能在模组生态跟进的同时尽快出可用包。
4. **可扩展** —— 新模组跟进后，能持续加入优秀模组而不破坏前三条。

第 1、2 条是**铁律**（下节详述）。第 3、4 条是效率目标，永远服从于铁律。

---

## 2. 铁律：原版双向直连

### 2.1 允许什么

本整合包的模组必须全部是 **client-side only** 或 **双方都可安全安装但对原版对端无要求** 的类型。
具体来说，允许存在：

- 纯客户端渲染 / 性能 / UI 模组（Sodium、Iris、Mod Menu 等）
- 客户端侧的行为辅助（Litematica、MiniHUD、Inventory Profiles 等）
- 客户端内置的服务端兼容逻辑，且**对原版服务端不发送任何自定义数据**

### 2.2 禁止什么

**严禁**引入任何满足以下任一条的模组：

| 禁止项 | 判定方法 |
|---|---|
| 注册自定义网络通道 | jar 内出现 `PayloadTypeRegistry.playC2S().register` / `ServerPlayNetworking.registerGlobalReceiver` / `ClientPlayNetworking.registerGlobalReceiver`（Fabric），或 Forge/NeoForge 的 `SimpleChannel` / `ChannelBuilder` |
| 改变握手 / 登录协议 | 引用 `ServerLoginNetworking` / `ClientLoginNetworking` / `LoginQueryRequest` / `ServerLoginNetworking.registerGlobalReceiver` |
| 要求对端安装 | `fabric.mod.json` 的 `environment` 非 `client`，且模组声明了自定义 payload；或模组文档明确写"服务端也需安装" |
| 服务端强制组件 | 模组在 `main` entrypoint 注册了玩家连接校验、注册表同步或自定义登录插件 |

**判定原则**：只要模组会向对端发送原版协议之外的数据包，或要求对端理解这些数据包，就是违反铁律——无论它"在单机里工作得多好"。

### 2.3 灰区处理

以下情况**不自动判定为违规**，但必须在 PR 描述里显式记录判定依据：

- 模组仅在客户端侧 mixin 原版的 `ClientboundCustomPayloadPacket` 做日志/包名美化，**未注册新通道**（例：`connectivity`）。
- 模组的 `environment` 是 `*`（双端皆可），但实际只做客户端优化、不主动发自定义包。
- 模组引用了自定义 payload 类，但只用于**读取和丢弃**未知包，而非发送。

灰区必须用 `python3 tools/scan_channels.py --explain <file>` 输出实际命中的类名后再判断，**不允许凭模组名称或描述下结论**。

### 2.4 每次变更都必须验证

任何增删模组的 PR 都必须附上：

```
python3 tools/scan_channels.py
```

的完整输出。扫描报 `BLOCK` 的模组不得合入；报 `REVIEW` 的必须在 PR 中写明人工判定结论。

---

## 3. AI 的权限边界

### 3.1 AI 可以自主做

- 读写 `mods/`、`resourcepacks/`、`shaderpacks/` 下的 `.pw.toml`
- 运行只读的校验与扫描脚本（`tools/` 下全部）
- 查询 Modrinth / CurseForge / GitHub 的公开 API 获取模组元数据
- 修改 `index.toml`、`pack.toml` 的哈希（**必须**通过重新计算，不能手改）
- 在 `feature/*`、`fix/*`、`chore/*` 分支提交
- 撰写 PR 描述、变更说明、模组调研结论
- 更新 `CHANGELOG.md`、`docs/` 下的文档

### 3.2 AI 必须停下来问

- **合并到 `main`** —— 由作者决定
- **修改 `pack.toml` 的 `version`** —— 发版号由作者定
- **导出并发布 `.mrpack`** —— 发布动作由作者执行
- **删除任何现有模组** —— 必须作者确认（可能是有意保留的）
- **引入新模组** —— AI 可以调研并给出建议，但加入动作需作者确认
- **修改 `AGENTS.md` 与 `tools/` 的判定规则** —— 属于约束本身，AI 不得自行放宽

### 3.3 AI 绝对不能做

- 放宽或绕过铁律判定
- 手写 `index.toml` 的哈希而不实际计算
- 直接把 `.jar` 提交进仓库（除 `overrides/` 下明确记录的例外，见 §5.3）
- 声称已经测试过游戏内表现 —— **游戏内测试是作者的职责**
- 在未实际运行的情况下声称"校验通过"

### 3.4 测试职责划分

| 类型 | 谁做 | 内容 |
|---|---|---|
| 静态校验 | AI | 哈希一致性、元数据完整性、铁律扫描、依赖闭包检查 |
| 构建验证 | AI | 能否成功 `packwiz refresh`、能否导出 `.mrpack`、包内文件是否可下载 |
| 游戏内测试 | **作者** | 启动、崩溃、按键冲突、界面、实际联机、性能 |

AI 只能在**不启动游戏**的前提下验证。AI 必须清楚地说"静态检查通过，未做游戏内验证"，
不得用"应该没问题"之类措辞模糊这一点。

---

## 4. 工具链规范 (packwiz)

### 4.1 基本原则

- **只通过 packwiz 管理模组**，`.pw.toml` 是唯一事实来源。严禁直接往 `mods/` 塞 `.jar`。
- 任何改动之后必须 `packwiz refresh`，否则 `index.toml` 与磁盘不一致。
- `packwiz.exe` 位于仓库根目录，**不提交进 git**（已加入 `.gitignore`）。

### 4.2 常用命令

```bash
# 新增模组（Modrinth）
./packwiz.exe mr add <slug-or-url>

# 新增模组（CurseForge）
./packwiz.exe cf add <slug-or-url>

# 删除模组
./packwiz.exe remove <name>

# 同步索引（任何改动后必须执行）
./packwiz.exe refresh

# 批量升级到最新版本
./packwiz.exe update --all

# 升级单个模组
./packwiz.exe update <name>

# 检查可升级项（不改文件）
./packwiz.exe update --all --dry-run

# 导出整合包
./packwiz.exe mr export
```

### 4.3 版本升级流程

```bash
# 1. 更新 pack.toml 里的 minecraft / fabric 版本（手工编辑或 packwiz 命令）
# 2. 接受新版本
./packwiz.exe settings acceptable-versions
# 3. 逐个尝试升级，观察哪些模组尚未跟进
./packwiz.exe update --all --dry-run
# 4. 实际升级
./packwiz.exe update --all
# 5. 同步索引
./packwiz.exe refresh
```

### 4.4 注意

- `packwiz refresh` 会重算所有哈希。**每次 refresh 后检查 diff**，
  若出现与你的改动无关的大面积哈希变动，说明有工具或格式问题，先查清再提交。
- `--dry-run` 的结果应配合 `tools/track_updates.py` 一起看，
  后者会标出"上游还没发布目标版本"的模组——这些是等生态跟进的主要阻塞项。

---

## 5. 仓库结构

```
packwiz/
├── AGENTS.md              # 本文件：AI 与人的共同约束
├── README.md              # 面向使用者与贡献者的说明
├── CHANGELOG.md           # 版本变更记录
├── pack.toml              # 整合包元数据（名称、版本、MC/Fabric 版本）
├── index.toml             # 文件索引（哈希清单，由 packwiz 生成）
├── mods/                  # 每个模组一个 .pw.toml
│   ├── sodium.pw.toml
│   └── ...
├── resourcepacks/         # 资源包 .pw.toml
├── shaderpacks/           # 光影 .pw.toml
├── overrides/             # 覆盖文件（配置、默认选项等）
│   └── ...
├── docs/                  # 开发文档
│   ├── workflow.md        # 日常开发流程
│   └── release.md         # 发版流程
├── tools/                 # 校验脚本
│   ├── verify_pack.py     # 哈希与索引一致性
│   ├── scan_channels.py   # 铁律扫描（网络通道检测）
│   ├── check_side.py      # side 字段合理性检查
│   └── track_updates.py   # 上游更新追踪
└── .github/workflows/
    └── validate.yml       # CI：每次 push / PR 自动校验
```

### 5.3 例外：无法通过 Modrinth/CurseForge 分发的模组

少数模组（作者定制构建、上游无公开分发）既不在 Modrinth 也不在 CurseForge。
这类模组的处理方式：

1. `.pw.toml` 使用 `url` 模式，URL 指向**本仓库的 GitHub Release**。
2. 由作者把 jar 上传到对应 Release。
3. `.pw.toml` 里保留一行注释标明"无上游分发渠道，需手动更新"。

**不允许**把这类 jar 直接提交进 git 仓库（会让仓库体积失控）。
当前属于此类的模组记录在 `docs/manual-mods.md`。

---

## 6. 提交与分支规范

### 6.1 分支命名

```
main               # 稳定版，只接受通过 PR 的合并
feature/<slug>     # 新增模组或功能
fix/<slug>         # 修复
chore/<slug>       # 维护性改动（文档、脚本、CI）
release/<version>  # 发版准备
```

### 6.2 提交信息

采用 Conventional Commits，**中文描述**：

```
<type>(<scope>): <描述>

[可选正文]

[可选脚注]
```

`type` 取值：`feat`、`fix`、`docs`、`chore`、`refactor`、`build`、`revert`

示例：

```
feat(mods): 新增 Sodium Extra 光影设置增强

fix(mods): 修正 MasaGadget 的 side 字段为 client

该模组 fabric.mod.json 声明 environment=client，
原 side="both" 会导致服务端元数据冗余。

chore(tools): 补充网络通道扫描的 Forge 特征

build: 升级至 Minecraft 26.3，fabric 0.19.5
```

### 6.3 提交粒度

- **一个模组的增删 = 一个提交**（便于出问题单独 revert）
- **不要**把"升级 MC 版本"与"新增模组"混在一次提交
- 每次提交前必须保证 `tools/verify_pack.py` 通过

### 6.4 PR 要求

PR 描述必须包含：

1. **变更摘要** —— 做了什么
2. **铁律影响评估** —— 新模组是否涉及网络通道（附 `scan_channels.py` 输出）
3. **验证情况** —— 跑过哪些脚本，结果如何
4. **未验证项** —— 明确写出"未做游戏内测试"

---

## 7. 文档索引

| 文档 | 内容 |
|---|---|
| `docs/workflow.md` | 日常开发：加模组、升级、修 bug 的完整步骤 |
| `docs/release.md` | 发版：从版本号到 Modrinth 发布的完整流程 |
| `docs/mc-upgrade.md` | MC 大版本升级的应对清单 |
| `docs/manual-mods.md` | 无上游分发渠道的模组清单与更新方法 |
| `docs/decisions/` | 架构决策记录（为什么选某个模组/方案） |

---

## 8. 遇到不确定时的处理

**默认倾向是保守。**

- 模组是否违反铁律有疑问 → 按违规处理，除非能给出明确证据证明安全
- 不确定某模组是否已被弃更 → 查 Modrinth/CurseForge 最后更新时间，超过一年未更新标记为"观察"
- 不确定能否升级 → 不升级，等上游明确支持
- 不确定是否该删某模组 → 不删，问作者

任何"看起来应该没问题"的判断，都必须转成"我实际验证了 X，结果是 Y"的形式。
