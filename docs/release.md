# 发版流程

## 版本号规则

Nitrogen 采用 `<主版本>.<次版本>` 形式（如 6.11、7.3）。

- **主版本**递增：跟随 Minecraft 大版本切换（1.21.10 → 26.x 属于大跨越）
- **次版本**递增：同一 MC 版本下的模组增删、配置调整

`pack.toml` 里的 `version` 字段是唯一事实来源。

## 完整流程

### 1. 确认目标 MC 版本

编辑 `pack.toml`：

```toml
[versions]
fabric = "<对应 fabric loader 版本>"
minecraft = "<目标 MC 版本>"
```

Fabric loader 版本查 https://fabricmc.net/develop/

### 2. 检查生态跟进情况

```bash
python3 tools/track_updates.py --mc <目标版本> --only-blocked
```

输出的"未跟进"列表决定了这一步的可行性：

- 若阻塞的是**核心模组**（Sodium、Iris、Fabric API）→ 等待，不要发版
- 若阻塞的是**可选模组**（装饰性、小众工具）→ 可以发版，在更新日志中说明
- 若阻塞的是**资源包/光影** → 通常不影响，它们的版本标注不严格

### 3. 升级模组

```bash
# 干跑
./packwiz.exe update --all --dry-run

# 实际升级（只影响走下载链接的模组）
./packwiz.exe update --all
./packwiz.exe refresh
```

打包分发的模组（`mods/` 下的 jar）**不会被 `update --all` 更新**，
需手动处理 —— 见 [bundled-mods.md](bundled-mods.md)。

### 4. 全量校验（缺一不可）

```bash
# ① 哈希与索引一致性 + 下载可达性
python3 tools/verify_pack.py --online

# ② 铁律扫描 —— 必须 BLOCK 0
python3 tools/scan_channels.py

# ③ side 复核 —— 必须"不一致 0"
python3 tools/check_side.py

# ④ 打包模组登记与布局检查
python3 tools/check_bundled.py
```

任何一项报错都**不要继续**。

### 5. 更新版本号

```bash
# 编辑 pack.toml 的 version 字段，例如 7.3 -> 7.4
./packwiz.exe refresh
python3 tools/verify_pack.py
```

### 6. 更新 CHANGELOG

在 `CHANGELOG.md` 顶部加入本次版本条目，写明：

- MC / Fabric 版本变化
- 新增的模组（附一句话说明用途）
- 移除的模组（附原因）
- 已知问题（尤其是"某模组尚未跟进"）

### 7. 提交并打标签

```bash
git add -A
git commit -m "build: 发布 <版本号>"
git tag -a v<版本号> -m "Nitrogen <版本号>"
git push origin main --tags
```

### 8. 导出 mrpack

```bash
./packwiz.exe mr export
```

产物是 `Nitrogen-<版本号>.mrpack`（已在 `.gitignore` 中）。

导出时注意观察 packwiz 的输出：

- `added to manifest` = 走下载链接
- `added to zip` = 被打包进 `overrides/`（非 Modrinth 来源）

若某个**应该走链接**的 Modrinth 模组显示 `added to zip`，说明它的
`url` 有问题，需检查元数据。反之，打包模组应当显示 `added to zip`。

导出后确认包里没有混入开发文件：

```bash
python3 -c "
import zipfile,sys
z=zipfile.ZipFile(sys.argv[1])
bad=[n for n in z.namelist() if n.startswith(('overrides/docs','overrides/tools','overrides/AGENTS','overrides/.github')) or '__pycache__' in n]
print('混入的开发文件:', bad or '无')
" Nitrogen-<版本号>.mrpack
```

### 9. 发布到 Modrinth

在 https://modrinth.com/modpack/nitrogen7/versions 新建版本：

- 上传第 8 步导出的 `.mrpack`
- 填写版本号、MC 版本、加载器（Fabric）
- 更新日志粘贴第 6 步的内容

打包的 jar 会随 mrpack 一起上传，无需额外步骤。

### 10. 作者测试（发布前必做）

**AI 不执行这一步。** 至少验证：

- [ ] 整合包能正常启动到主菜单
- [ ] 新建世界能进入、能退出
- [ ] `Open to LAN` 后，**未装模组的原版客户端**能加入
- [ ] 用本包能连上一个**原版服务器**
- [ ] 按键无冲突（`mods/` 里控制类模组多，易冲突）
- [ ] 光影能正常切换

第 3、4 条是铁律的直接验证，**每次发版都要重做**。

## 回滚

发现问题时：

```bash
git revert <提交>
# 或
git reset --hard v<上一个正常版本>
./packwiz.exe refresh
```

Modrinth 上的版本可以设为 "unlisted" 或删除，避免玩家继续下载有问题的版本。
