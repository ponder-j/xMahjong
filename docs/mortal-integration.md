# Mortal 社区模型接入

选用 [VoidShine/mortal-298k](https://huggingface.co/VoidShine/mortal-298k)；这是社区自行训练的模型，不能等同于官方线上 Mortal 4.1。模型卡的强度指标为作者自报，本项目未独立复现。

| 项目 | 固定信息 |
|---|---|
| Hugging Face revision | `dbbea7e3d34f99ec43fc4834ab7f2aaaed70b6ee` |
| 文件 | `mortal_298k.pth`，130,774,416 字节 |
| SHA-256 | `bfb3a6c072aa0bfd4171a9cdc77cb6c02ae42cde920843f9e5784394f23447d8` |
| 配置 | Mortal v4，ResNet 40 blocks × 192 channels；四人半庄 |
| 发布许可 | AGPL-3.0；模型目录保留原始模型卡及许可 |
| 推理代码 | Equim-chan/Mortal `0cff2b52982be5b1163aa9a62fb01f03ce91e0d2` |
| 运行方式 | Docker 内 Python 3.12、PyTorch 2.9.1 CPU、原生 libriichi |

## 安装

```powershell
.\scripts\setup-mortal.ps1
# 若 Docker 需要本机代理：
.\scripts\setup-mortal.ps1 -Proxy http://host.docker.internal:18997
.\scripts\start-background.ps1 -Restart
```

Linux/macOS：`sh scripts/setup-mortal.sh`，再重启本机服务。脚本会下载固定 revision、在流式下载中计算 SHA-256、校验成功后原子写入最终文件，并保存 `provenance.json`。不使用随机初始化权重作为替代。权重和配置放在被 Git 忽略的 `models/mortal-298k/`。

下载器和配置器可独立运行：

```powershell
uv run python scripts/download-mortal.py
docker build -f tools/mortal.Dockerfile -t xmahjong/mortal:local .
uv run python scripts/setup-mortal.py
```

模型目录以只读方式挂载到推理容器 `/mnt`；API 服务不加载 PyTorch，Mortal 也不读取 LLM 密钥。加载由上游的 `torch.load(weights_only=True, map_location='cpu')` 完成。CPU 推理与本机 llama.cpp 的 GPU 推理分开运行。

`setup-mortal.py` 会再次校验本地文件哈希、确认镜像存在，然后更新 `config.local.json` 的 Mortal 命令、模型名称、revision 与哈希；保留现有 Akochan 和 LLM 设置。若原先已配置其他 Mortal 命令，会先在本地 `data/` 备份配置。

## 验证

```powershell
uv run python scripts/verify-mortal.py
uv run python scripts/integration-smoke.py --require-both
```

第一条使用上游真实牌谱的多个决策快照，检查 Mortal 成功返回、分布归一化、原始分数有限、弃牌符合当前合法集合，以及玩家实际动作被保留；普通摸牌局面同时要求 Akochan 成功。吃碰后阶段是 Akochan 上游不支持的独立时点，必须明确报告 unsupported。第二条验证本地 Web API、双模型、全候选 LLM 解释、追问和反事实。真实雀魂链接的账号要求是独立问题，Mortal 安装成功不会解除雀魂下载鉴权。

可加 `--scan-disagreements` 扫描更多真实决策，发现分歧后保存首个样本，供复查。实际验证结果分别写入 `artifacts/mortal-verification.json` 与 `artifacts/integration-result.json`。
