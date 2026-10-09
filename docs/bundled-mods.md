# 打包分发模组的维护

Modrinth 只接受 `cdn.modrinth.com` 的下载链接。因此不在 Modrinth 上的
模组必须把 jar 打包进去。本文档说明这些模组怎么维护。

## 分发模型

`packwiz mr export` 会这样处理各类来源（已用真实 packwiz 实测）：

| 来源 | 导出结果 |
|---|---|
| Modrinth | 写进 manifest 的下载链接 |
| CurseForge | 打包成 jar |
| 非白名单域名（forgecdn.net 等） | 打包成 jar |
| github.com / gitlab.com | 走下载链接（在白名单内） |
| **`mods/` 下的裸 jar** | **打包成 jar** |

所以规则很简单：**要打包的模组，jar 直接放 `mods/` 下。**

## 关键陷阱

```bash
# 正确 ✓
mods/connectivity-fabric-26.3-7.7.jar
#   -> 导出为 overrides/mods/connectivity-fabric-26.3-7.7.jar

# 错误 ✗ 会变成 overrides/overrides/mods/...，玩家装了不生效
overrides/mods/connectivity-fabric-26.3-7.7.jar
```

这是实测确认的行为。`tools/check_bundled.py` 会检查并报错。

## 当前清单

见仓库根目录的 `bundled-mods.toml`，那里是唯一事实来源。

大致情况（7.3）：

| 模组 | 来源 | 许可证 | 打包原因 |
|---|---|---|---|
| Connectivity | CurseForge | **ARR** | CF 链接不被 Modrinth 接受 |
| Cupboard | CurseForge | **ARR** | Connectivity 的前置 |
| MasaGadget | GitHub fork | LGPL-3.0 | 26.3 构建无公开 release |
| Modern UI Port | GitHub | LGPL-3.0+ | 非官方移植，无 release 产物 |
| Oh My Minecraft Client | GitHub fork | LGPL-3 | 0.7.1 构建未公开 |
| Eating Animation Fork | GitHub fork | MIT | 包内 5.1.0 未公开发布 |

## 更新某个模组

没有自动流程，步骤：

1. **取到新 jar**
   - CurseForge：到模组页面 Files 页下载
   - GitHub fork：到对应仓库的 Release 或 Actions 产物

2. **核对是否真的不在 Modrinth 上**（万一作者补发到 Modrinth 了，
   就应该改回链接模式以省掉打包）：

   ```bash
   python3 -c "
   import hashlib,sys
   print(hashlib.sha1(open(sys.argv[1],'rb').read()).hexdigest())
   " new.jar
   ```
   拿这个 sha1 去 `https://api.modrinth.com/v2/version_file/<sha1>?algorithm=sha1` 查。

3. **替换 jar**（注意文件名变化）

   ```bash
   rm mods/旧文件.jar
   cp new.jar mods/
   ```

4. **更新 `bundled-mods.toml`** 里的 `file`、`source_file_id`（若有）等字段

5. **重新生成索引并校验**

   ```bash
   ./packwiz.exe refresh
   python3 tools/check_bundled.py
   python3 tools/verify_pack.py
   ```

6. **在 `CHANGELOG.md` 记录**

## 许可证注意

打包分发属于**再分发**行为。ARR（保留所有权利）许可证的模组在打包前
应确认已获作者授权。

`tools/check_bundled.py` 会对 ARR 模组给出提示。当前 Connectivity 与
Cupboard 属于此类 —— 项目此前已在 Modrinth 发布过含这两个模组的版本
且通过审核，但严格来说这个授权问题需要你自己判断。

## 仓库体积

`mods/` 下的 jar 会进 git，仓库体积随之增长。当前约 27MB，
其中 Modern UI 独占 24MB。

若增长过快，可选方案：

- **Git LFS** —— 把 `*.jar` 交给 LFS 管理
- **改回链接模式** —— 若能找到可用的公开直链（github.com 在白名单内）

新增打包模组前先看一眼体积。

## 长期方向

打包模组是维护负担（无自动更新、需手动传 jar、仓库变大）。建议：

- 定期查 Modrinth 是否已收录某个模组，收录了就改回链接模式
- 向上游提 PR 让作者支持新版本，一旦官方发布 release 就能回到链接模式
- 若某模组长期无人维护且阻碍升级，考虑移除
