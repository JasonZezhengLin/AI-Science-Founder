# DSI 集群部署 & 跑真实验流程

账号 zezhenglin，家目录 /home/zezhenglin，用 general 分区（12 小时时限）。

## 一、把代码传上集群（在你 Windows PowerShell 里跑）

假设这个包解压在 Windows 的 C:\Users\57239\Downloads\cluster_deploy

```powershell
# 整个目录传到集群家目录
scp -r C:\Users\57239\Downloads\cluster_deploy login.ds:/home/zezhenglin/founder
```

（会问 CNetID 密码。传完后集群上路径是 /home/zezhenglin/founder）

## 二、在集群上建 Python 环境（登录节点上做，只做一次）

```bash
ssh login.ds
cd /home/zezhenglin/founder

# 建 conda 环境
source /opt/conda/etc/profile.d/conda.sh
conda create -y -n founder python=3.10
conda activate founder

# 装依赖（生态系统 + 真实验需要的 torch 等）
pip install -r requirements.txt
pip install torch transformers datasets
```

注意：建环境和 pip install 是「轻」操作，登录节点允许。但**别在登录节点跑实验**。

## 三、填 API 凭证

```bash
cd /home/zezhenglin/founder
nano .env
```

把 .env 填成（你的 yunwu key）：
```
S2_API_KEY="你的S2key"
HF_ENDPOINT="https://hf-mirror.com"
OPENAI_BASE_URL="https://yunwu.ai/v1"
OPENAI_API_KEY="你的yunwu-key"
```
Ctrl+O 存，Ctrl+X 退。

## 四、先用最小规模配置（先跑通再放大）

```bash
cp bfts_config_minimal.yaml bfts_config.yaml
```

## 五、提交真实验作业

```bash
sbatch submit_real.sbatch
```

会返回一个 job id，比如 `Submitted batch job 123456`。

## 六、看进度 / 管理作业

```bash
squeue -u zezhenglin                      # 看你的作业排队/运行状态
tail -f ai_system_runs/slurm_123456.out   # 实时看日志（换成你的 jobid）
scancel 123456                            # 要取消就用这个
```

作业状态 ST 列含义：PD=排队等 GPU，R=正在跑，CG=收尾。

## 七、先跑最小验证，再放大

submit_real.sbatch 默认 NUM_FOUNDERS=2 MAX_CYCLES=1，先确认这个能跑通
（真训练、真 peer review、出真 metric）。通了之后放大：

```bash
# 改大规模：编辑 submit_real.sbatch 顶部，或用 --export 覆盖
sbatch --export=ALL,NUM_FOUNDERS=2,MAX_CYCLES=2 submit_real.sbatch
```

要换更强的卡（比如 a100/h100），改 submit_real.sbatch 里的：
```
#SBATCH --gres=gpu:a100:1
```
（不指定型号就是 general 里任意一张）

## 八、断点续传

literature_db 持久化在 ai_system/literature_store/db.json。如果作业被 12 小时时限
打断，重新 sbatch 会自动从已有文献库续上（日志会显示「从 db.json 加载 N 篇论文」）。

## 常见问题

- **作业一直 PD 排队**：GPU 被占满，等。或换 dev 分区调试（但 dev 只有 10 分钟时限，
  且要改 #SBATCH --partition=dev --time=00:10:00）。
- **conda: command not found**：先 `source /opt/conda/etc/profile.d/conda.sh`。
- **import torch 失败**：环境没装好，重做第二步的 pip install torch。
- **调 yunwu 报错**：检查 .env 的 key 和 OPENAI_BASE_URL 填对没；登录节点 curl 是通的。
- **报错看不懂**：把 ai_system_runs/slurm_<jobid>.err 的内容贴给我。

## 这个包修复了哪些（已全部测试通过）

14 项修复：Bug1 无GPU全拒、Bug2 funding聚齐竞争、Bug4 ideation retry、Bug7 JSON解析、
Bug8 容错JSON、Bug9→embedding语义检索、单founder评审降级、测试库隔离、断点续传、
token cached防御、bfts模型改qwen 等。详见 TOTAL_BUGFIX_NOTES（如随包）。
