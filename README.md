# dpgen-cluster-kit —— NaGeSe DPA4C × dpgen1 × 集群 VASP 分发 部署包

> 内容: 你的补丁版 dpgen 源码(含 dpa4c patch) + 多账号 VASP 分发器 + NaGeSe 项目全套配置。
> 目标: 在新电脑上 3 步完成部署: 解压 → configure → setup → sbatch。

## 包内容

```
dpgen-cluster-kit/
├── README-部署.md          ← 本文件
├── setup.sh                ← 一次性: 建 conda 环境 dpgen + 安装补丁版源码
├── configure.sh            ← 路径适配: 生成 project/ 可运行副本(可重复运行)
├── templates/              ← 参数化模板({{PROJECT}} 等占位符) + 资产
│   ├── run_NaGeSe.json / run_machine.json / dpgen.sh
│   ├── dp_ft_shim.sh / fp_wrapper.sh / vasp_env.sh
│   ├── fp_dispatch.py / accounts.json / fp_routes.py / README-分发.md
│   └── INCAR_run / POTCAR_{Na,Ge,Se} / DPA4C-*.pt2(基座 41MB)
├── dpgen-source/           ← 补丁版 dpgen 源码 + dpa4c.patch(115 行改动存档)
└── project/                ← configure.sh 生成, 在此提交任务
```

## 部署步骤

```bash
# 0. 解压(如果拿到的是 tar.gz)
tar xzf dpgen-cluster-kit.tar.gz && cd dpgen-cluster-kit

# 1. 路径适配(交互式, 回车用默认; 会生成 project/ 并检查依赖)
./configure.sh

# 2. 创建 dpgen 环境(一次性; 已有则跳过; 需要 pip 网络源)
./setup.sh

# 3. 提交生产
cd project && sbatch dpgen.sh
```

> 注意: 首次解压后包内**没有** project/ 目录(或含打包机路径的旧副本), 必须
> 先跑 `./configure.sh` 生成适配本机的 project/ 再提交。setup.sh 需要网络
> (pip 拉依赖; 内网机器先配镜像源)。

监控: `squeue` / `tail -n2 iter.*/00.train/*/lcurve.out` / `python3 fp_routes.py`(DFT→账号路由)

## 无法打包、需目标机自备的部分

| 依赖 | 说明 |
|---|---|
| **AIMD 初始数据** | `3-AIMD-data/`(training_data 11200帧 + validation_data 2800帧 + 35 个 POSCAR), configure 时给路径 |
| **deepmd 训练环境** | conda `deepmd-GPU-DPA4`: dp(--pt-expt/dpa4c) + lmp + `dpa4c-slice-type-map` + `~/Software/lammps-deepmd` 编译库。含 GPU 编译二进制, 需按原机方式重建 |
| **VASP 可执行** | 本地 GPU 版(`vasp.6.4.3/bin/vasp_gam`) + CPU 版(`cpu_vasp.6.4.3_vtst`)+ NVHPC/oneAPI 环境(vasp_env.sh/fp_wrapper.sh 引用); 许可证软件不随包分发 |
| **超算 SSH 密钥** | `~/Software/yau_ssh/*.txt` 5 把(集群 222.25.80.22 各账号); 集群侧各账号需有自己的 vasp544_bin |
| **本地 SLURM** | MindForge 分区(可选; 没有 sbatch 可直接 `conda activate deepmd-GPU-DPA4 && dpgen run ...`) |
| NVIDIA 驱动 + CUDA stubs | GPU 训练/AOT 用(configure 可指定) |

## 新机可能要微调的

- `project/accounts.json`: 集群账号/配额/核数/ALGO 补丁/本地并发
- `project/run_machine.json`: fp `group_size`(=task_max/并发数)
- `project/dpgen.sh`: 若 deepmd 环境名不同, 改 conda activate 行

## 版本记录

- 2026-09-15: 初版。dpgen 0.13.4.dev4(dpa4c patch); 分发器含 ALGO=Normal 补丁/
  ulimit 修复/任务-账号路由日志/本地并发闸(2)/满载排队。已在 5-dpgen_test 端到端
  实测(300 任务: kf 83/jm 73/wwg 72/本地 72, 全部收敛)。
