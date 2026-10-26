# XMahjong 架构与实施记录

调研日期：2026-10-26。先调研、确定边界，再实现。目标：本地复盘，不接入实时对局。

## 依赖核查

| 项目 | 核查版本 / 来源 | 许可 | 接口与运行条件 | 集成决定 |
|---|---|---|---|---|
| [mjai-reviewer](https://github.com/Equim-chan/mjai-reviewer) | `2dc5ec5c8b28517cfb45f57eb21536d9a8f67aa9` | Apache-2.0 | Rust 2024；convlog 处理天凤6 JSON、鸣牌、杠、立直；reviewer 支持 JSON 输出 | 原样 vendoring convlog，以小型 stdin/stdout Rust CLI 调用，保留 LICENSE |
| [Mortal](https://github.com/Equim-chan/Mortal) | `0cff2b52982be5b1163aa9a62fb01f03ce91e0d2` | AGPL-3.0-or-later（代码） | Rust libriichi + Python/PyTorch；`mortal.py <actor>`、`MORTAL_REVIEW_MODE=1`，每条事件回复一个 JSON，`meta.mask_bits/q_values` | 独立容器/子进程；官方无附带权重，现接入已校验的 VoidShine/mortal-298k 社区 checkpoint，固定 revision 与 SHA-256；可替换其他兼容权重 |
| [Akochan](https://github.com/critter-mj/akochan) | `53188a0b926fbab38177f88c3cd87d554cf412af` | 自定义日文利用规约，非 OSI 许可 | C++11 / OpenMP / Boost；参数目录；`system.exe pipe_detailed tactics.json <actor>`；仅自摸或他家弃牌/加杠时输出数组 | 使用未修改上游独立进程，Docker 本地构建；不发布上游二进制。个人非商业研究用途；其他用途应核对原文及取得授权 |
| [tensoul-py](https://github.com/ssttkkl/tensoul-py) | PyPI 0.1.8 | MIT | ms-api、WebSocket；旧登录协议需适配当前 Unity 客户端 | 复用牌谱转换器，独立子类负责官方版本检测、新网关握手、CN 账号登录与下载；允许替换并保留 JSON/MJAI 导入 |
| [UnityPy](https://github.com/K0lb3/UnityPy) | 1.25.4，uv.lock | MIT | Python 3.12 Windows wheel 及其解压依赖，本机已安装并实际解析官方元数据 | 只读取公开版本资源，不执行游戏脚本；程序与资源版本分别用于登录 |
| [MahjongRepository/mahjong](https://github.com/MahjongRepository/mahjong) | uv.lock | MIT | Python 标准型、七对子、国士向听与手牌评分 | 独立证据计算；不把牌效计算冒充 AI |

评分核查依据：`mjai-reviewer/src/review/{mortal,akochan}.rs`、上游 [FAQ](https://github.com/Equim-chan/mjai-reviewer/blob/master/faq.md)。Mortal Q 不是局收支或胜率；偏好分布为 `softmax(Q / temperature)`，必须同时展示温度。Akochan 的 `pt_exp_total` 是其自身目标下的期望值，并非通用胜率；`total_houjuu_hai_prob_now` 等字段原样保留。跨模型只比较动作及排名，不直接相减原生评分。

## 数据流

雀魂链接 → 本机登录下载适配器 → tensoul 转换 → 天凤6 JSON → convlog → MJAI → 状态归约器 → 决策快照。

快照与经过遮蔽的历史分别输入 Mortal、Akochan；并行运行两个适配器，输出不可用、失败、超时或真实候选，不静默替换。所有合理候选取并集：任一概率模型偏好 ≥1%、任一非概率模型 Top-K、玩家实际动作。补充计算全部合法弃牌的证据以便反事实比较。

证据计算器只读取自己的手牌、牌河、副露、宝牌指示牌、分数和立直状态。可见枚数包含自己手牌、公开牌；被鸣牌的弃牌只计一次。剩余枚数是「未见枚数」，不是实际牌山枚数。现物只对相应对手的荣和安全，不保证不被自摸或不能鸣牌。无实测风险模型时不估造放铳概率。

LLM 接收封闭证据字典，返回候选逐项的优势、劣势、适用条件、比较与分歧解释；每个结论引用证据 ID。未通过结构/引用校验时拒绝该输出并退回确定性事实报告。自然语言真实性无法由引用校验完全证明，界面保留原始证据供核查。追问携带同一局面及有限会话历史，禁止读取未来事件。

## 模块与边界

- `logs.py`：导入与转换；`state.py`：MJAI 状态和决策。
- `majsoul.py`：CN 登录、新网关握手与下载；`majsoul_versions.py`：读取官方 Unity 程序/资源版本元数据。
- `engines.py`：原生进程协议、评分转换与来源信息；新增引擎遵循 EngineResult 契约。
- `evidence.py`：向听、进张、宝牌/赤牌保留、现物证据和单步弃牌反事实。
- `analysis.py`：候选合并、按排名识别分歧、证据封装。
- `explainer.py`：OpenAI 兼容请求与结构化校验。
- `app.py`：本机 API、SQLite 存储、Web 静态服务。

MVP 重点保证弃牌和鸣牌后的弃牌证据正确；鸣牌/杠/和牌等模型输出保留，但未实现的反事实明确不可用，不模拟未来牌山。立直后的弃牌强制摸切；吃碰后禁止喰替。复杂和牌/杠合法性最终依赖已配置引擎，不以启发式代码替代完整裁判。

分歧规则：至少两个成功返回候选的引擎才能判定；首选相同为共识；首选不同但互相均在前二为轻微分歧；其他为明显冲突。该规则是可解释的排名规则，不是统计显著性或模型正确性的证明。

## 部署与硬件

FastAPI 同源静态 Web，无前端构建依赖。SQLite 持久化原始牌谱；模型结果带版本与原始输出缓存。进程超时、并发上限、上传大小上限。默认只监听 127.0.0.1；无多用户鉴权，不应直接暴露公网。

RTX 4070 12GB、32GB RAM：Akochan 走 CPU/OpenMP（默认 4 线程）；Mortal 官方 CLI 当前走 CPU，GPU 可通过替代命令接入；远程 LLM 不占显存。本地 llama.cpp 仅作兼容性测试。实际吞吐取决于用户权重与策略设置，不预先承诺延迟。

## 验收阶段

1. 导入与可见信息回放、真实日志重放测试。
2. 原生 Akochan 与 Mortal 社区模型真实推理、合法动作及分布校验；无配置时仍明确标记不可用。
3. 向听/进张/现物与候选并集测试；无后见信息测试。
4. llama.cpp 解释、追问与错误处理测试。
5. Web 交互测试；真实天凤样本及用户授权的真实雀魂半庄均已通过双模型、全候选解释、追问和反事实流程。

网关联调发现：旧 `version.json` 的 `0.11.252.w` 只用于读取线路配置，不能作为新版 Unity 登录版本。官方网页和资源清单实际检测为程序 4.0.51 / 资源 0.16.289；适配器动态检测而非固定这些值。`gateways → /api/clientgate/routes → Route.requestConnection` 使用 Web 平台、秒级时间戳，并检查握手获准。登录使用独立程序/资源版本和 `WebGL_2022-…` 标识，随后确认登录。此前匿名下载返回 1004；配置用户授权账号并更新协议后，真实登录、下载及 API 导入均已通过，取得 6 局、511 个 MJAI 事件。凭据仅保存在本机 `.env`，不写入测试夹具或 LLM 请求。

llama.cpp 联调：本机 b11205 / local-qwen 的 JSON grammar 与 `<think>` 前缀冲突。实际采用 JSON `{` 前缀、`continue_final_message=true`、`add_generation_prompt=false`、`echo=true`，并为每个候选构造有界 JSON Schema，完整解释与追问均已通过。远程普通 API 不启用该本机兼容模式。

Mortal 接入记录：`scripts/setup-mortal.ps1` 从固定 Hugging Face revision 下载权重并校验 SHA-256，原生 PyTorch/libriichi 容器已成功加载 v4、40×192 网络。历史 MJAI 带 `can_act=false`，目标决策才运行网络；保持完整历史状态但避免反复评价前缀。真实样本中已观测到两模型共识和明显冲突；第 2 巡 Mortal 首选打 3s、Akochan 首选打 E。吃碰后的独立时点由 Akochan 上游 `Selector` 明确禁止，因此适配器返回 unsupported，不能把上一时点的复合动作分数伪装为当前评分。
