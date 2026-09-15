#!/bin/bash
# dpgen train/freeze 包装器 (微调工作流, Project3 Na-Ge-Se):
#   train  -> 透传 dp --pt-expt (iter0 加 --finetune old/init.pt2, iter>=1 加 --init-model)
#   freeze -> 把 118-type checkpoint 切片成 3-type (Na,Ge,Se) 后再 freeze,
#             产出 frozen_model.pt2; 原始 checkpoint 不动, 供下一轮 --init-model 续用
# 切片工具: dpa4c-slice-type-map, 安装于 deepmd-GPU-DPA4 环境 bin/ (需环境已激活)
# 由 run_machine.json 的 train.command 调用, cwd = dpgen 训练任务目录
BASE={{PROJECT}}
SLICE={{DEEPMD_ENV}}/bin/dpa4c-slice-type-map

while [ $# -gt 0 ] && [[ "$1" == -* ]]; do shift; done
SUB=$1
shift

if [ "$SUB" = "train" ]; then
    INP=$1
    python3 - "$INP" "$BASE/DPA4C-Plus-OMat24-v20260819.pt2" <<'EOF'
import json, sys, zipfile
inp, base = sys.argv[1], sys.argv[2]
j = json.load(open(inp))
tm = json.loads(zipfile.ZipFile(base).read("model/extra/model.json"))["model"]["type_map"]
if j["model"].get("type_map") != tm:
    j["model"]["type_map"] = tm
    json.dump(j, open(inp, "w"), indent=2)
    print(f"type_map 已还原为基座 {len(tm)} 元素 (dpgen 会用 jdata 3 元素覆盖, 训练需 118)")
EOF
    exec dp --pt-expt train "$@"
elif [ "$SUB" = "freeze" ]; then
    CKPT=model.ckpt.pt
    [ -f "$CKPT" ] || CKPT=checkpoint/model.ckpt.pt
    if [ ! -f "$CKPT" ]; then
        echo "dp_ft_shim: 找不到 checkpoint ($CKPT)" >&2
        exit 1
    fi
    TMP=$(mktemp -d)
    "$SLICE" "$CKPT" "$TMP/model.ckpt.pt" Na,Ge,Se > slice_freeze.log 2>&1 || {
        echo "dp_ft_shim: checkpoint 切片失败, 见 slice_freeze.log" >&2
        cat slice_freeze.log >&2
        rm -rf "$TMP"
        exit 1
    }
    dp --pt-expt freeze -c "$TMP" -o frozen_model.pt2 >> slice_freeze.log 2>&1 || {
        echo "dp_ft_shim: freeze 失败, 见 slice_freeze.log" >&2
        cat slice_freeze.log >&2
        rm -rf "$TMP"
        exit 1
    }
    rm -rf "$TMP"
    [ -f frozen_model.pt2 ] || { echo "dp_ft_shim: frozen_model.pt2 未生成" >&2; exit 1; }
else
    exec dp --pt-expt "$SUB" "$@"
fi
