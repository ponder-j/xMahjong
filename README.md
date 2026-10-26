# XMahjong 交叉复盘

本地运行的日本麻将牌谱复盘工作台：保留 Mortal 与 Akochan 各自的评分，独立计算证据，逐候选解释，并支持中文追问。

**本地双模型流程已通过真实天凤及用户授权的真实雀魂半庄验收。** Mortal 使用已校验的 VoidShine/mortal-298k 社区训练权重，Akochan 使用原生引擎；候选解释、追问和反事实已联通。社区模型不等同于官方线上 Mortal 4.1，其强度未经本项目独立评测。雀魂使用本机 CN 账号登录，动态读取新版 Unity 客户端元数据；不提供匿名下载保证。

## 启动

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、Docker Desktop（Linux containers）。Web 无 Node/npm 构建依赖。

```powershell
cd C:\Codes\XMahjong
.\scripts\build-engines.ps1
.\scripts\setup-mortal.ps1
.\scripts\start-background.ps1
```

打开 [本地工作台](http://127.0.0.1:8765)。首次构建会下载 Rust、Boost 并编译；已有镜像可直接启动。仅做 MJAI 导入与独立证据计算时可以不构建 Docker 引擎。

如果 Docker 构建须走本机代理：

```powershell
.\scripts\build-engines.ps1 -Proxy http://host.docker.internal:18997
```

Linux/macOS：`sh scripts/build-engines.sh`、`sh scripts/setup-mortal.sh`，再 `sh scripts/start.sh`。Docker 守护进程需运行。Windows 前台运行仍可使用 `scripts/start.ps1`；后台服务通过 `scripts/start-background.ps1 -Restart` 重启，通过 `scripts/stop-background.ps1` 停止。

## 使用流程

1. 粘贴雀魂四人半庄链接，或导入天凤6 JSON / MJAI JSONL / MJAI 数组。首次可点“体验真实示例牌谱”。示例取自上游真实天凤测试牌谱，**不代表雀魂端到端验收已完成**。
2. 选择复盘座位与决策时点。默认只列自己决策；“含应对”可展示他家弃牌/加杠后的应对。
3. 点击“分析当前局面”。对照候选排名、原始评分、向听与未见进张；点击候选查看分项解释。
4. 点击“生成中文 AI 解释”。每个合理候选均须有优势、劣势、适用条件与横向比较；没有证据的部分明确未知。
5. “继续追问”只使用当前决策的证据和本局面的有限对话历史。切换决策会清空聊天上下文。
6. 弃牌反事实只重算合法弃牌后的即时证据，不复用原牌谱未来结果，也不声称已经重推理模型。

## 雀魂链接

首次可复制 `.env.example` 为 `.env`；已有 `.env` 时直接编辑，填写：

```dotenv
XMAHJONG_MAJSOUL_USERNAME=your-cn-account
XMAHJONG_MAJSOUL_PASSWORD=your-password
```

运行 `scripts/start-background.ps1 -Restart` 加载修改。使用 CN 原生账号密码；第三方授权或短信验证码登录尚不支持。新版握手发送 `platform=Web`，动态区分程序/资源版本并使用 `WebGL_2022-…` 登录标识，完成登录确认后获取牌谱。`ResGameRecord.data_url` 会由下载器读取，转换仍复用 tensoul。凭据只保留本机，不发送给 LLM。匿名牌谱 `_2` 的混淆编号目前未实现还原，请使用原始 UUID 链接或导出的 JSON。

上游协议、风控和账号限制可能变化。未配置凭据、版本被拒绝、限流会分别提示，不使用来源不明的公共代理。备用 JSON 导出需要第三方工具，详见 [登录与导入排错](docs/majsoul-login.md)。只有标准四人半庄在本版本支持范围；三麻、东风与特殊活动规则不支持。

## Mortal 接入

[Mortal 官方源码](https://github.com/Equim-chan/Mortal) **不附带训练权重**。默认接入路线改为公开的 [VoidShine/mortal-298k](https://huggingface.co/VoidShine/mortal-298k) 社区模型（AGPL-3.0），固定 revision 和 SHA-256：

```powershell
.\scripts\setup-mortal.ps1
# Docker 需要代理时：
.\scripts\setup-mortal.ps1 -Proxy http://host.docker.internal:18997
.\scripts\start-background.ps1 -Restart
```

安装器会下载并校验权重、保存许可和来源记录、构建 Python/PyTorch + libriichi 的独立容器，并只更新 Mortal 配置。模型目录只读挂载，使用上游 `weights_only=True` 安全加载。当前走 CPU；本机 llama.cpp 继续使用 GPU。详细来源及步骤见 [社区模型接入](docs/mortal-integration.md)。

如需手动接入其他 checkpoint，按 [官方构建文档](https://mortal.ekyu.moe/user/build.html) 安装 PyTorch、编译 libriichi，并用该 Python 环境执行 `mortal.py`：

`config.local.json`（从 `config.example.json` 复制）中的 `mortal` 示例：

```json
{
  "command": ["C:/your-mortal-env/python.exe", "C:/your-Mortal/mortal/mortal.py", "{actor}"],
  "cwd": "C:/your-Mortal/mortal",
  "env": {"MORTAL_CFG": "C:/Codes/XMahjong/data/mortal-config.toml"},
  "version": "填写实际 checkpoint 的版本与来源",
  "weight_sha256": "填写实际权重的 SHA256",
  "timeout": 120
}
```

复制上游 `config.example.toml` 为自己的配置，设置 `[control].state_file` 为实际权重。计算哈希：`Get-FileHash -Algorithm SHA256 C:\path\to\checkpoint.pth`。此适配器使用 `MORTAL_REVIEW_MODE=1`，历史事件传入 `can_act=false` 只更新状态，目标时点才运行神经网络；在目标决策后终止，不触发 CLI EOF 时的 GRP 全局排名模型阶段。

适配器解码 46 维 mask、Q 值、赤五及 kan_select；保留原始输出。使用独立进程，替换 `command` 即可接入兼容实现。权重或配置改变时应更新版本与哈希；这些字段参与缓存键。社区安装器在下载和配置时校验实际哈希；手动填写的哈希属于用户声明的来源信息。

## Akochan 接入

构建脚本从上游固定 commit `53188a0...` 原样构建。本地命令使用 `mjai_log /dev/stdin <actor>` 一次性评价目标前缀，避免每次重新计算整个历史；上游 `pipe_detailed` 也是支持的输出格式。默认策略为上游 `setup_mjai.json`，CPU/OpenMP 4 线程。若需调策略，可将自备的配置以 Docker 只读挂载替换 `/opt/akochan/setup_mjai.json`，并更新 `version`。

`pt_exp_total`、放铳风险等字段保留在原始输出中。规则动作可能没有数值，此时显示“规则动作，未评分”，不填零。

上游独立评价入口只接受自摸、他家弃牌或加杠阶段。吃碰后或立直宣言后的独立弃牌阶段会显示 `unsupported`，而 Mortal 可继续评价；应在前一个应对/立直前局面查看 Akochan 的完整复合动作，不复用旧分数冒充当前评分。

**Akochan 是自定义非商业许可，不是 MIT。** 请核对其 [日文利用规约](https://github.com/critter-mj/akochan/blob/master/LICENSE)。本项目提供本地构建方式，不发布 Akochan 二进制或参数。详见 [依赖声明](THIRD_PARTY_NOTICES.md)。

## LLM 配置

Web 右上角“连接设置”可以修改并持久保存 `base_url`、`api_key`、`model`。配置原子写入本机 `data/llm-settings.json`，重启服务后自动恢复；该目录被 Git 与 Docker 构建上下文忽略，密钥不回显，也不写入浏览器存储。留空保留现有密钥。保存失败时维持原运行配置。

“测试连接”会实际调用所选模型的 `/chat/completions` 并检查 JSON 输出，不再只以模型列表可访问作为成功依据。阿里云 Qwen 会自动关闭 llama.cpp 兼容模式，并以 `enable_thinking=false` 配合结构化解释。

也可手工使用 `.env` 初始化：

```dotenv
XMAHJONG_LLM_BASE_URL=https://your-provider.example/v1
XMAHJONG_LLM_API_KEY=your-key
XMAHJONG_LLM_MODEL=your-model
```

配置优先级为：界面保存的 `data/llm-settings.json` > `config.local.json` 显式字段 > 环境变量 / `.env` > 默认值。要重新使用手动配置，可先通过界面修改，或移走已保存的 LLM 配置文件。默认本地示例为 `http://127.0.0.1:18080/v1`，`local-qwen`。远程 API 通常**关闭** Thinking 兼容模式，并将 `llm_assistant_prefill` 设为 `""`。

本机 `C:\LocalLLM\start-server-background.ps1 -TextOnly` 可启动已部署的 llama.cpp。当前 Thinking 模型使用 JSON 开头 `{` 作为 assistant prefill，配合 `continue_final_message=true`、`add_generation_prompt=false` 与 JSON Schema grammar，避免思考段消耗输出额度。兼容模式统一处理这些参数。远程普通 API 使用 JSON mode。小模型逐候选请求，避免上下文过长；输出结构/引用校验失败会重试一次，然后明确退回确定性事实报告。

LLM 不收到对手暗牌、未来事件、账号密码或 API 密钥。事实文字由服务端计算证据生成，推测引用已有证据，未提供的数字会拒绝；对同一候选已计算却漏引的速度/宝牌/现物指标，可确定性补齐引用，不能借用另一候选或模型评分为其解释。数值允许合理四舍五入，百分比不可与非概率混用。这无法形式化证明自然语言推断正确，所以原始证据始终可展开核查。请勿将“带引用”理解为绝对真实性保证。

## 评分与分歧

- 候选取并集：概率偏好 ≥1%（含边界）、非概率 Top-K（默认 5）、玩家实际动作。无模型时另列“独立牌效对照”，明确不是 AI 推荐。
- Mortal 偏好为 `softmax(Q / temperature)`，默认温度 0.1；原始 Q 与温度同时保留。偏好不是胜率。
- Akochan 原始期望值不转概率，不与 Mortal Q 相减。
- 两个引擎首选首动作相同：共识。首选不同但互相在前二：轻微分歧。其他：明显冲突。任一引擎未成功：证据不足。
- Akochan 可能返回“立直/鸣牌 + 弃牌”的复合动作；Mortal 可能逐阶段输出。候选保留完整动作，不伪称 Mortal 评价过它没有评价的后续弃牌；分歧规则仅比较首动作，并注明该边界。
- 向听复用 mahjong，涵盖标准型、七对子、国士。进张为减少向听的**未见牌枚数**，不偷看实际牌山。
- 宝牌/赤牌保留量只是打点线索，不等于役、最终番符或期望得分。现物仅对对应对手的荣和提供安全依据；其他危险率未知。

## 工程与测试

```powershell
uv sync --locked
uv run pytest -q
uv run ruff check backend tests
node --check frontend/app.js
```

可选 Web 验证：`npm install --no-save --package-lock=false playwright` 后运行 `node scripts/browser-smoke.cjs`。Windows 使用已安装的 Edge；截图输出到 `artifacts/`。完整运行检查：`uv run python scripts/integration-smoke.py`（依赖本机服务、Akochan 镜像、LLM）。

Mortal 原生快照验证：`uv run python scripts/verify-mortal.py`。完整双模型运行检查：`uv run python scripts/integration-smoke.py --require-both`。

`data/xmahjong.sqlite3` 保存牌谱与评分缓存。引擎命令、版本、声明权重哈希、温度与 Top-K 均参与缓存键。失败/超时不缓存。LLM 解释与聊天在当前界面会话中显示，刷新后可重新生成。API 文档：[本地 /docs](http://127.0.0.1:8765/docs)。

后端位于 `backend/xmahjong`；前端为同源原生 HTML/CSS/JS，便于在 Windows 本地部署。模块边界与依赖调研见 [架构文档](docs/architecture.md)，实际验证记录见 [验收记录](docs/validation.md)。

当前高级功能边界：单步弃牌反事实已实现；鸣牌/杠/和牌的完整反事实、完整打点期望、对手风险模型、未来对局模拟尚未实现。模型输出负责复杂动作的完整规则合法性；本项目未重写完整麻将裁判。独立弃牌合法性覆盖立直强制摸切、手牌持有、吃碰喰替。

默认只监听 `127.0.0.1`，有同源请求保护，没有公网多用户鉴权。不要直接暴露在公网；部署到其他场景需自行加认证与网关。
