#!/usr/bin/env python3
"""格式化查看 fp_dispatch_routes.log: python3 fp_routes.py [过滤词]"""
import json
import sys
from pathlib import Path

log = Path(__file__).resolve().parent / "fp_dispatch_routes.log"
if not log.is_file():
    sys.exit(f"暂无路由日志: {log}")
pattern = sys.argv[1] if len(sys.argv) > 1 else ""
rows = []
for line in log.read_text().splitlines():
    r = json.loads(line)
    if pattern and pattern not in json.dumps(r, ensure_ascii=False):
        continue
    rows.append(r)
print(f"{'时间':<19} {'任务':<18} {'账号':<14} {'作业':>6} {'退出':>4} {'耗时':>7}")
for r in rows:
    acct = r["account"].split("@")[0].replace("_", "")
    print(f"{r['time']:<19} {r['task']:<18} {acct:<14} {r['job_id'] or '-':>6} "
          f"{r['exit_code'] or '-':>4} {r['elapsed_sec']:>5}s")
if rows:
    from collections import Counter
    c = Counter(r["account"].split("@")[0] for r in rows)
    print(f"\n共 {len(rows)} 条 | " + " | ".join(f"{k} {v}" for k, v in c.most_common()))
