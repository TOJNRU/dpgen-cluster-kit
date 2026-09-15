#!/bin/bash
# configure.sh —— 新机器部署适配: 把 templates/ 的占位符回填为真实路径, 生成可运行的 project/
# 用法: ./configure.sh   (交互确认, 回车用默认值)
set -e
KIT="$(cd "$(dirname "$0")" && pwd)"
TPL="$KIT/templates"
PROJ="$KIT/project"

echo "=== dpgen-cluster-kit 路径适配 ==="
echo "（回车 = 使用方括号内默认值）"
ask() {  # ask 变量名 提示 默认值
    read -r -p "$2 [$3]: " v || true
    v=${v:-$3}
    eval "$1=\"\$v\""
}
ask PROJECT "项目运行目录(生成的配置所在)" "$KIT/project"
ask DATA    "AIMD 初始数据目录(需含 training_data/validation_data/POSCAR)" "$HOME/kingston/Project3/1_DeepMD/3-AIMD-data"
ask SOFTWARE "软件根目录(hpc_sdk/vasp/oneapi/lammps-deepmd 所在)" "$HOME/Software"
ask SSH_KEYS "超算 SSH 密钥目录" "$HOME/Software/yau_ssh"
ask DEEPMD_ENV "deepmd 环境路径(dp/lmp/dpa4c-slice-type-map)" "$SOFTWARE/anaconda3/envs/deepmd-GPU-DPA4"
ask DPGEN_ENV "dpgen 工作流环境路径(conda, 由 setup.sh 创建)" "$SOFTWARE/anaconda3/envs/dpgen"
ask CONDA    "anaconda 根目录" "$SOFTWARE/anaconda3"
ask CUDA_STUBS "CUDA stubs 目录(AOT 链接用, 没有可留空)" "/usr/local/cuda-12.8/targets/x86_64-linux/lib/stubs"

for v in PROJECT DATA SOFTWARE SSH_KEYS DEEPMD_ENV DPGEN_ENV CONDA; do
    val="${!v}"
    [ -n "$val" ] || { echo "错误: $v 为空"; exit 1; }
done
# CUDA_STUBS 允许留空(无 GPU AOT 需求时)

mkdir -p "$PROJ"
python3 - "$TPL" "$PROJ" \
    "{{PROJECT}}=$PROJECT" "{{DATA}}=$DATA" "{{SOFTWARE}}=$SOFTWARE" \
    "{{SSH_KEYS}}=$SSH_KEYS" "{{DEEPMD_ENV}}=$DEEPMD_ENV" \
    "{{DPGEN_ENV}}=$DPGEN_ENV" "{{CONDA}}=$CONDA" "{{CUDA_STUBS}}=$CUDA_STUBS" <<'PYEOF'
import shutil, sys
from pathlib import Path
tpl, proj = Path(sys.argv[1]), Path(sys.argv[2])
pairs = [a.split("=", 1) for a in sys.argv[3:]]
TEXT_FILES = {"run_NaGeSe.json", "run_machine.json", "dpgen.sh", "dp_ft_shim.sh",
              "fp_wrapper.sh", "vasp_env.sh", "fp_dispatch.py", "accounts.json",
              "fp_routes.py", "README-分发.md"}
for f in tpl.iterdir():
    if not f.is_file():
        continue
    if f.name in TEXT_FILES:
        s = f.read_text()
        for old, new in pairs:
            s = s.replace(old, new)
        (proj / f.name).write_text(s)
        print(f"  {f.name}")
    else:  # 二进制资产原样拷贝
        shutil.copy2(f, proj / f.name)
        print(f"  {f.name} (资产, 原样拷贝)")
PYEOF

echo
echo "=== 检查关键依赖 ==="
fail=0
[ -d "$DATA/training_data" ] && echo "✓ 初始数据" || { echo "✗ 初始数据缺失: $DATA"; fail=1; }
[ -x "$DEEPMD_ENV/bin/dp" ] && echo "✓ deepmd 环境(dp)" || { echo "✗ deepmd 环境缺失: $DEEPMD_ENV (见 README '无法打包部分')"; fail=1; }
[ -d "$SSH_KEYS" ] && echo "✓ SSH 密钥目录" || { echo "✗ SSH 密钥缺失: $SSH_KEYS"; fail=1; }
[ -f "$PROJ/DPA4C-Plus-OMat24-v20260819.pt2" ] && echo "✓ 基座模型" || { echo "✗ 基座缺失"; fail=1; }
if command -v sbatch >/dev/null; then echo "✓ 本地 SLURM"; else echo "⚠ 本地无 sbatch(可用 bash 直接跑 dpgen, 见 README)"; fi
echo
[ $fail -eq 0 ] && echo "配置完成 → $PROJ (cd 过去 sbatch dpgen.sh 即可)" \
                 || echo "配置已生成但有关键依赖缺失, 按 README 补齐后再运行"
