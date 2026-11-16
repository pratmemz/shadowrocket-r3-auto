# Shadowrocket R3 自动同步（Mac + iOS）

## 目标

以 Johnshall 官方 `release/sr_cnip.conf` 作为每日上游，在**不丢失原版新增规则**的前提下，自动叠加已在 Mac 上通过浏览器 DNS 检测的 R3 定制内容。生成同一个 `sr_cnip_r3_auto.conf` 供 Mac 和 iOS 订阅。**这不等于 iOS 真机和 Mac 全应用零泄漏的验收**。

上游地址：`https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip.conf`

默认构建时间：每天 **北京时间 09:30**（GitHub Actions 使用 UTC 01:30；不保证分钟级准时）。

## 一、部署到你自己的 GitHub（只需一次）

1. 登录 GitHub，新建一个 **公开** Repository，建议名 `shadowrocket-r3-auto`，默认分支 **main**。不要上传私人节点订阅、token、证书或密码。
2. 将本 ZIP 内的内容放到仓库根目录。必须保留隐藏文件夹 `.github/workflows/`；其中的 `update-shadowrocket.yml` 是真正执行定时任务的文件。可以通过 `git` 或 GitHub Desktop 上传。
3. 到仓库 **Settings → Actions → General → Workflow permissions**，允许 GitHub Actions 使用 `Read and write permissions`（如选项可用）；保存。
4. 进入仓库 **Actions → R3 Shadowrocket upstream sync → Run workflow**，手动首次运行。只有成功时才会提交 `sr_cnip_r3_auto.conf` 与 `build_manifest.json`。
5. 后续 Actions 每日运行。若上游突然变更了 DNS 或 GEOIP/FINAL 结构、下载失败或单元测试失败，会报错并**不会替换原有文件**。

> 仓库地址举例：`https://github.com/YOURNAME/shadowrocket-r3-auto`
> **实际订阅 URL**（用你的用户名替换 YOURNAME）：
>
> `https://raw.githubusercontent.com/YOURNAME/shadowrocket-r3-auto/main/sr_cnip_r3_auto.conf`
>
> 不要把这个地址替换成 Johnshall 原版 URL，否则更新会覆盖 R3 改动。

## 二、Mac 和 iOS 使用同一个修正版

在 Shadowrocket 的「配置」页点 `+`，粘贴上面的 **raw.githubusercontent.com** 链接并下载；选中这份配置作为当前配置，保持全局路由为「配置」。当前 Mac 使用已验证的 `None (TUN)`，Chrome 的 QUIC 为 `Disabled`；**这项 Chrome 设置不属于 .conf，在 iOS 不会自动复制**。

在 Shadowrocket「设置 → 自动更新 → 配置」开启可用的后台更新，配置更新频率可选每日。iOS 还应在系统「设置 → 通用 → 后台 App 刷新」允许 Shadowrocket；iOS 计划任务受系统调度限制，不能保证每天精准刷新。也可从配置页面手动「更新」进行验证。

先保存现有已验证的 `sr_cnip_r3_fix.conf` 作为回退。iOS 初次使用，应分别验证 Safari、Telegram、ChatGPT 等 App，不要仅凭 Chrome/Mac 的 DNS 结果断言 iOS 完全无泄漏。

## 三、文件说明

- `.github/workflows/update-shadowrocket.yml`：GitHub 每日调度、测试、下载、构建、提交。
- `scripts/build_r3.py`：从**最新上游**增量合成 R3；无第三方 Python 依赖；遇到关键兼容性变化失败关闭。
- `patches/priority_proxy.txt`：高优先级代理域名（Google/YouTube/检测网站等）。
- `patches/domestic_direct.txt`：R3 的国内常见域名直连规则。
- `tests`：验证所生成规则保留原版、必需规则和域名优先级；包含你 2026-11-16 上传的原始文件及 Mac 已用 R3 的测试基线。
- `sr_cnip_r3_auto.conf`：附带的**本地生成初始样本**，供离线检查；第一次 GitHub Actions 运行才获取当日最新 GitHub 上游和正确自更新 URL。

## 四、安全与隐私注意

- 保留 R3 原有 `dns-server` 国内 DoH 是为了国内直连速度；只有代理请求的解析路径可望经代理端处理。当前浏览器 DNS 检测良好，但不保证所有系统/应用 DNS 全无绕行。
- Chrome QUIC 被禁用只是本次 Mac 特定网络的兼容性方案，不意味着 iOS UDP/QUIC 已验收。
- 自动构建器不会修改节点信息，也不包含任何节点订阅。公开 GitHub 仓库会公开规则和模板（**不含用户节点**）。
- GitHub Actions 计划运行可能延迟/跳过；上游更新可能临时不可用；请检查 Actions 运行记录，首次务必手动验证。
- 如果需要自有域名，可将最终配置托管至你自己的静态 HTTPS 服务，但必须同步更改 `update-url` 目标，不能直接指向原版。

## 五、本地自测（不需要上网）

在根目录执行：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_r3.py --source tests/fixtures/original_user.conf --output /tmp/r3-local-test.conf
```

如果要本地拉取最新原版：

```sh
python3 scripts/build_r3.py --fetch --output /tmp/r3-latest-preview.conf
```

> 本地 preview 因未提供自己的 GitHub 仓库地址，不会写入有效的 `update-url`。Github Actions 部署时会自动设置为本仓库 raw 文件。
