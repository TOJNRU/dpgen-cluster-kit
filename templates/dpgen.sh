#!/bin/bash
#SBATCH -J dpgen
#SBATCH --ntasks=16
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH -p MindForge
#SBATCH --output=dpgen_job.out --error=dpgen_job.err

cd  $SLURM_SUBMIT_DIR
export TF_CPP_MIN_LOG_LEVEL=2
export CUDA_ALLOW_TF32=1
export TF32_ENABLE=1
export TORCH_ALLOW_TF32=1

# dpgen 0.13.4.dev (补丁版, dpa4c/pt-expt 支持) 装在 deepmd-GPU-DPA4
source ~/Software/anaconda3/etc/profile.d/conda.sh
conda activate deepmd-GPU-DPA4

# pip 版 deepmd-kit 缺 libdeepmd_op_cuda.so, 借用本地编译的 lammps-deepmd
TORCHLIB=$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")
export LD_LIBRARY_PATH={{SOFTWARE}}/lammps-deepmd/libdeepmd_c/lib:$TORCHLIB:${LD_LIBRARY_PATH}

# 训练线程/显存优化 (与 dp_train_single.sh 相同)
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8
export DP_INTRA_OP_PARALLELISM_THREADS=1
export DP_INTER_OP_PARALLELISM_THREADS=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# VASP FP 任务经 source_list 加载 vasp_env.sh; 这里只做栈/兼容设置
export NO_STOP_MESSAGE=yes
ulimit -s unlimited

# CUDA stubs 只进 LIBRARY_PATH (AOT freeze 链接期用)。
# 严禁放进 LD_LIBRARY_PATH: stubs 里的 libcuda.so 会遮住真驱动,
# warp/nvalchemiops (dpa4c 邻居表) 枚举不到 CUDA 设备 -> IndexError
export LIBRARY_PATH={{CUDA_STUBS}}:${LIBRARY_PATH}

dpgen run run_NaGeSe.json run_machine.json > log.out
