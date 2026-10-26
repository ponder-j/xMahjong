# 雀魂牌谱下载与登录

`1004` 出现在牌谱获取阶段时，应先检查下载请求是否已登录、账号是否有访问权限。它与 Mortal 权重和 LLM API Key 无关。XMahjong 使用本机 CN 原生账号密码登录；QQ / Bilibili 等第三方授权、短信验证码登录不属于这个适配器的支持范围。登录方式限制也见 [tensoul 上游说明](https://github.com/ssttkkl/tensoul-py)。

## 本机保存凭据

在项目根目录 `.env` 中设置以下两个字段。已有 `.env` 时编辑原文件，不要覆盖其他配置：

```dotenv
XMAHJONG_MAJSOUL_USERNAME='your-cn-account'
XMAHJONG_MAJSOUL_PASSWORD='your-password'
```

修改后运行：

```powershell
cd C:\Codes\XMahjong
.\scripts\start-background.ps1 -Restart
```

凭据用于雀魂官方网关登录，不发送给 LLM，不返回前端。`.env` 已被 Git 忽略。未配置完整凭据时，程序会直接给出配置提示，避免反复匿名请求。

## 新版客户端兼容

旧 `tensoul 0.1.8` 的登录标识和网关握手无法完整描述新版 Unity 客户端。本项目保留其牌谱转换器，替换下载和登录层：

- 从官方网页读取程序版本，从官方资源清单定位并读取资源版本。通过 UnityPy 解析元数据，不执行下载的脚本，不硬编码当前发布版本。
- 网关握手使用秒级时间戳、Web 类型及 `platform=Web` 字段，并检查连接是否获准。旧版 `ms-api` 缺失的 protobuf 字段由本机适配器保留，不改动安装包。
- 登录分别发送 `client_version.package` 与 `client_version.resource`；`WebGL_2022-…` 使用资源版本。登录成功后完成确认，再请求牌谱。
- 请求有总超时，连接关闭有独立时限；登录失败和限流不会自动重试。

相关协议变化可参考 [上游兼容说明](https://github.com/ninkjin/Majsoul-Mortal-Analyzer#tensoul-本地账号密码获取) 与 [InjusticeJudge 的协议更新讨论](https://github.com/Longhorn-Riichi/InjusticeJudge/issues/37)。是否可用以本机对官方服务的实际验证为准。

## 错误处理

| 提示 | 处理方式 |
|---|---|
| 尚未配置完整登录凭据 | 补齐 `.env` 的两个字段并重启 |
| 1004 / 登录状态或权限无效 | 检查账号登录方式、登录结果以及该牌谱的访问权限 |
| 151 / 客户端版本被拒绝 | 更新下载器；不能据此判断密码错误 |
| 540 / 限流 | 等待后手动重试，或导入已经导出的 JSON |
| 版本元数据无法识别 | 官方格式可能变化；更新适配器或改用 JSON |

## JSON 导入备用方式

如果无法使用 CN 原生账号，可在已经登录的雀魂网页中使用支持新版 Unity 客户端的导出工具。一个公开实现是 [downloadlogs.user.js](https://files.riichi.moe/mjg/other/downloadlogs_script/downloadlogs.user.js)：安装到 Tampermonkey，刷新雀魂，打开目标牌谱，按 `s` 下载天凤6 JSON，然后在 XMahjong 点击“导入 JSON / MJAI”。这属于第三方导出脚本，雀魂没有原生的天凤6 JSON 导出按钮；本项目未替用户安装此脚本。

只支持标准四人半庄。匿名分享链接 `_2` 的编号还原尚未实现，需使用含原始 UUID 的分享链接或导出的 JSON。
