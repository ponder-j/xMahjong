# 实际验证记录

日期：2026-10-26，Windows / RTX 4070 12GB / 32GB RAM。所有结果均为本机实际执行；没有将协议测试桩用作生产模型。

| 项目 | 结果 | 证据 / 边界 |
|---|---|---|
| Python 自动化测试 | 39 项通过 | 覆盖 LLM 持久化、错误脱敏；增补雀魂缺少凭据时不发匿名请求、程序/资源版本区分、密码摘要、新版握手和错误码提示 |
| Ruff / JS 语法 | 通过 | `ruff check backend tests`、`node --check frontend/app.js` |
| convlog 本地构建 | 通过 | Docker `xmahjong/convlog:local`，上游固定来源，Cargo.lock 保存依赖版本 |
| 上游复杂牌谱状态验证 | 20 个日志、2310 个事件通过 | 四个视角均重建局面并检查可见牌不超过四枚；含鸣牌、杠、抢杠、多人和牌。部分测试日志为东风，仅用于转换/状态测试，不宣称支持范围扩展 |
| Akochan 真实推理 | 通过 | 未修改上游，固定 commit `53188a0...`；首个真实天凤测试局面返回 12 个候选，Top-5 留作分析；原始期望值未概率化 |
| Mortal | 真实推理通过 | VoidShine/mortal-298k，固定 revision、SHA-256 校验成功；Python 3.12 / PyTorch 2.9.1 CPU / 原生 libriichi。实际网络 v4，40 blocks × 192 channels；单元测试中的合成输出仍仅用于协议契约 |
| 双模型分歧 | 真实共识与明显冲突均已观测 | 东 1 局第 1 巡同选 2p；第 2 巡 Mortal 选 3s、Akochan 选 E，按既定排名规则判为明显冲突；未声称哪方必然正确 |
| 分歧局面的中文解释 | 通过 | 第 2 巡五个合理候选全部覆盖，LLM 输出通过结构及证据校验；用时约 34 秒，原始报告与解释保存在 `artifacts/conflict-report.json` |
| 吃碰后独立评价 | Mortal 通过；Akochan 明确不支持 | 上游 Akochan `set_selector` 仅接受 tsumo/dahai/kakan，适配器显示 unsupported；分歧为证据不足，不伪造评分 |
| llama.cpp 解释 | 通过 | 本机 `local-qwen`，实际生成五个候选的结构化中文解释，引用和候选覆盖校验通过 |
| llama.cpp 追问 | 通过 | 实际 OpenAI 兼容 `/chat/completions`，以当前证据回答现物问题 |
| 单步弃牌反事实 | 通过 | 与对应候选独立证据一致；非法弃牌被拒绝；未使用未来结果 |
| 桌面/手机浏览器 | 通过 | Playwright + 本机 Edge，导入、分析、候选切换、反事实、前后步、连接设置；无 JS 控制台异常；390px 视口无横向溢出 |
| 雀魂真实链接下载 | **通过** | 使用用户授权的 CN 原生账号，官方元数据检测为程序 4.0.51 / 资源 0.16.289；握手、登录、登录确认、牌谱下载成功。用户提供的四人金之间半庄含 6 局，API 导入返回 511 个 MJAI 事件 |
| 真实天凤样本的双模型全流程 | **通过** | `integration-smoke.py --require-both` 确认两个真实引擎、五候选 LLM 解释、追问及反事实均成功 |
| 完整双模型 + 雀魂验收 | **通过** | 在上述真实雀魂牌谱的第二巡运行两个真实引擎，保留 5 个合理候选；阿里云 Qwen 的全候选解释、追问和单步反事实均通过，用时约 36 秒 |

真实天凤测试牌谱：`2019050417gm-0029-0000-4f2a8622`，316 个 MJAI 事件。来源见 `tests/fixtures/README.md`。此外，真实雀魂验收使用用户明确授权的牌谱；账号、密码及完整牌谱数据仅保存在本机忽略目录/配置中，不写入公开测试夹具。

`scripts/integration-smoke.py --require-both` 在本机依次调用真实 Mortal、Akochan、LLM 全候选解释、LLM 追问和反事实 API。默认真实天凤样本记录约 42 秒；使用 `--replay-id <已导入编号> --decision-id <决策编号>` 可验证已有真实牌谱，也可用 `--majsoul-link <授权分享链接>` 验证含下载的流程。真实雀魂第二巡记录约 36 秒，结果为 **complete**。性能数字仅描述指定局面和本机配置，不是完整半庄吞吐承诺。

复现命令：

```powershell
uv run pytest -q
uv run ruff check backend tests
node --check frontend/app.js
uv run python scripts/validate-upstream-fixtures.py
uv run python scripts/verify-mortal.py --scan-disagreements
uv run python scripts/integration-smoke.py --require-both
node scripts/browser-smoke.cjs
```

`--require-both` 可强制集成脚本在 Mortal 未运行时失败。真实双模型验收前不能仅凭默认脚本的退出码宣称完成。

本地运行结果：`artifacts/integration-result.json`（天凤）、`artifacts/integration-real-replay.json`（授权雀魂）；`data/majsoul-check.json` 与 `data/majsoul-api-import-check.json` 分别记录脱敏的登录下载/服务导入结果；桌面/手机截图：`artifacts/review-desktop.png`、`artifacts/review-mobile.png`。这些目录和缓存数据库不提交到源码。

原生快照与分歧扫描记录：`artifacts/mortal-verification.json`。社区模型来源和安装方式见 `docs/mortal-integration.md`；本次推理不代表对其绝对强度或模型卡自报指标的独立评测。

阿里云连接验证：2026-10-26，当前配置模型 `qwen3.8-flash` 的模型列表与实际 Chat Completions 请求均返回 HTTP 200，JSON 输出检查通过。配置已保存到本地；服务重启后重新读取密钥、端点和模型，再次通过实际生成测试。验证记录在 `data/llm-check.json` 与 `data/llm-check-after-restart.json`，不含密钥。阿里云请求关闭本机 llama.cpp 前缀兼容选项，使用非思考模式生成 JSON。
