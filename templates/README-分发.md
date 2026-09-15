# 5-dpgen 集群 VASP 分发(2026-09-14 接入, 5-dpgen_test 实测验证)

## 改动清单
- 新增 `fp_dispatch.py`(分发器) + `accounts.json`(5账号配置)
- `run_machine.json`: 仅 fp 节 command 换成分发器, group_size 150→30
- `run_NaGeSe.json`: **未改动**(保留渐进温度/信任区间0.15/fp_task_min 60)
- 其余资产(dp_ft_shim/fp_wrapper/INCAR/POTCAR/基座)未动

## 运行(与原来完全一样)
```bash
sbatch dpgen.sh        # 或原启动方式
```

## 分发逻辑
每任务: 随机轮询5账号(探测含排队,配额2) → 64核 sbatch → 回传OUTCAR
- 集群满 → 本地 fp_wrapper(上限2: 1GPU+1CPU) → 都满 → 20s重试排队
- 任务归属记录: fp_dispatch_routes.log(本目录, JSONL) + 各任务 fp.log
- INCAR 补丁: 集群自动改 ALGO=Normal(Fast 在 5.4.4 静默失败), 本地不变
- jm 已修复: vasp544 + 作业脚本含 ulimit -s unlimited

## 监控
```bash
tail -f fp_dispatch_routes.log                 # 任务→账号 路由记录
grep RECORD iter.*/02.fp/task.*/fp.log         # 任务级记录
ssh 各账号 "squeue -u 用户名"                    # 集群作业
```

## 调节
- 并发总量: run_machine.json fp.resources.group_size (300/N)
- 账号配额/核数/启停: accounts.json (max_jobs/cpu_per_node/enabled)
- 本地并发上限: accounts.json local_max_concurrent
