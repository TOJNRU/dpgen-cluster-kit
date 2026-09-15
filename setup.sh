#!/bin/bash
# setup.sh —— 创建 dpgen conda 环境并安装补丁版源码(在 kit 解压后运行一次)
set -e
KIT="$(cd "$(dirname "$0")" && pwd)"
CONDA="${CONDA:-$HOME/Software/anaconda}"
ENVNAME="${DPGEN_ENV_NAME:-dpgen}"

if [ ! -f "$CONDA/etc/profile.d/conda.sh" ]; then
    # 尝试常见位置
    for c in "$HOME/anaconda3" "$HOME/miniconda3" "/opt/anaconda3" "/opt/miniconda3"; do
        [ -f "$c/etc/profile.d/conda.sh" ] && CONDA="$c" && break
    done
fi
echo "使用 conda: $CONDA"

source "$CONDA/etc/profile.d/conda.sh"
if conda env list | grep -qE "^$ENVNAME "; then
    echo "环境 $ENVNAME 已存在, 跳过创建"
else
    conda create -n "$ENVNAME" python=3.12 -y
fi

conda activate "$ENVNAME"
pip install -e "$KIT/dpgen-source"
dpgen --version && echo "dpgen 环境就绪: conda activate $ENVNAME"
echo
echo "提醒: 训练/探索还需要 deepmd 环境(含 dp/lmp/dpa4c-slice-type-map),"
echo "      该环境含编译二进制无法直接打包, 见 README-部署.md 第 3 节。"
