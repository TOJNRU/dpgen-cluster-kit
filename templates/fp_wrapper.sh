#!/bin/bash
# dpgen fp 任务启动器 (2026-09-12 基准测试结论):
#   GPU 独占槽 (flock), 抢不到的后备走 CPU np8 (oneAPI 环境)。
#   实测: GPU x1 + CPU np8 ~= 0.98 任务/分钟, 预算 ~10 核。
# 由 run_machine.json 的 fp.command 调用, cwd = fp 任务目录。
source {{PROJECT}}/vasp_env.sh
export NO_STOP_MESSAGE=yes

GPU_VASP={{SOFTWARE}}/vasp.6.4.3/bin/vasp_gam
CPU_VASP={{SOFTWARE}}/cpu_vasp.6.4.3_vtst/bin/vasp_gam
ONEAPI={{SOFTWARE}}/intel/oneapi
IMPI=$ONEAPI/mpi/2021.13
OMPI_MR=$(command -v mpirun)   # vasp_env.sh 放进 PATH 的是 hpcx mpirun

exec 9>>/tmp/fp_gpu_slot.lock
if flock -n 9; then
    OMP_NUM_THREADS=8 "$OMPI_MR" -np 1 "$GPU_VASP"
else
    OMP_NUM_THREADS=1 \
    LD_LIBRARY_PATH=$ONEAPI/2024.2/lib:$ONEAPI/mkl/latest/lib/intel64:$IMPI/lib:$LD_LIBRARY_PATH \
      "$IMPI/bin/mpirun" -np 8 "$CPU_VASP"
fi
