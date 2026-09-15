#!/usr/bin/env python3
"""fp_dispatch: dpgen1 的 VASP 多账号分发器（单任务粒度）。

由 machine.json 的 fp.command 调用, cwd = fp 任务目录(内含 INCAR/POSCAR/
POTCAR/KPOINTS)。流程:
  1. OUTCAR 已存在则直接退出(幂等, 支持 dpgen1 断点重跑)
  2. 抢本地账号槽位 -> ssh squeue 复核远程空位(含排队, 配额 2/账号)
  3. 有空位: tar 上传任务目录 -> sbatch VASP -> 轮询 -> 回传产物
  4. 无空位/远程失败: 本地兜底(默认 bash fp_wrapper.sh, 绝对路径见 accounts.json)
  5. 全失败: 非零退出(dpdispatcher 记为失败任务)

多实例并行安全: dpdispatcher 按 group_size 分组并发调用本脚本,
本地槽位目录(每账号 max_jobs 个)防止超额提交, 槽位带超时自愈。
"""

import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

DONE_FLAG = "_DPGEN_DONE"
EXIT_FLAG = ".exit_code"
COUNTED_STATES = "R,PD,CF,CG"
SLOT_STALE_SEC = 4 * 3600
POLL_SEC = 20
JOB_TIMEOUT_SEC = 4 * 3600


class Account:
    def __init__(self, conf):
        self.username = conf["username"]
        self.host = conf["host"]
        self.port = int(conf.get("port", 22))
        self.key = str(Path(conf["private_key_file"]).expanduser())
        self.root = conf["remote_root"]
        self.max_jobs = int(conf.get("max_jobs", 2))
        self.queue = conf.get("queue_name")
        self.cpus = int(conf.get("cpu_per_node", 32))
        self.sources = conf.get("source_list", [])
        self.command = conf.get("command") or "mpirun -np {nproc} vasp_std"
        self.enabled = conf.get("enabled", True)
        self.incar_patch = conf.get("incar_patch", {})
        self.name = f"{self.username}@{self.host}"

    def ssh_base(self):
        return ["ssh", "-i", self.key, "-p", str(self.port), "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
                f"{self.username}@{self.host}"]

    def run(self, cmd, timeout=60):
        try:
            p = subprocess.run(self.ssh_base() + [cmd], capture_output=True,
                               text=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except (subprocess.TimeoutExpired, OSError) as e:
            return 1, "", str(e)

    def remote_used(self):
        """squeue 计数(运行+排队), 失败返回 None(视为满载)."""
        ret, out, _ = self.run(
            f"squeue -h -u {shlex.quote(self.username)} -t {COUNTED_STATES} | wc -l")
        if ret != 0:
            return None
        try:
            return int(out.strip())
        except ValueError:
            return None


class Slot:
    """本地槽位: mkdir 原子抢占, mtime 超时自愈."""

    def __init__(self, account, idx):
        self.path = Path.home() / ".dpgen1_fp_slots" / f"{account.username}.{idx}"
        self.held = False

    def acquire(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.mkdir()
            self.held = True
            return True
        except FileExistsError:
            try:
                age = time.time() - self.path.stat().st_mtime
                if age > SLOT_STALE_SEC:
                    shutil.rmtree(self.path, ignore_errors=True)
                    return self.acquire()
            except OSError:
                pass
            return False

    def release(self):
        if self.held:
            shutil.rmtree(self.path, ignore_errors=True)
            self.held = False


def upload(acct, local_dir, remote_dir):
    # tar -m: 不恢复 mtime, 规避本地/集群时钟偏差的时间戳告警
    cmd = (f"tar chzmf - -C {shlex.quote(str(local_dir))} . | "
           + " ".join(shlex.quote(x) for x in acct.ssh_base())
           + f" 'mkdir -p {shlex.quote(remote_dir)} && tar xzmf - -C {shlex.quote(remote_dir)}'")
    return subprocess.run(["bash", "-c", cmd]).returncode == 0


def download(acct, remote_dir, local_dir):
    """打包 job_dir 回来, 把 <tag>/task/* 与 slurm-job.log 提升到任务目录."""
    rp, rn = os.path.split(remote_dir)
    tmp = Path(local_dir) / f".dl_{rn}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    cmd = (" ".join(shlex.quote(x) for x in acct.ssh_base())
           + f" 'cd {shlex.quote(rp)} && tar czmf - {shlex.quote(rn)}'"
           + f" | tar xzmf - -C {shlex.quote(str(tmp))}")
    if subprocess.run(["bash", "-c", cmd]).returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    back = tmp / rn
    ok = False
    for sub in back.glob("task/*"):
        if sub.is_file() or sub.is_symlink():
            if sub.name in (DONE_FLAG, EXIT_FLAG, "job.slurm"):
                continue
            dst = Path(local_dir) / sub.name
            dst.unlink(missing_ok=True)
            dst.write_bytes(sub.read_bytes())
            if sub.name == "OUTCAR" and sub.stat().st_size > 0:
                ok = True
    for extra in back.glob("slurm-job.log"):
        shutil.copy2(extra, Path(local_dir) / "slurm-job.log")
    shutil.rmtree(tmp, ignore_errors=True)
    return ok


def job_script(acct, tag, job_dir):
    # -D 必须是绝对路径(sbatch 不展开 #SBATCH 行里的变量)
    lines = ["#!/bin/bash", f"#SBATCH -J fpd-{tag}",
             f"#SBATCH -D {shlex.quote(job_dir)}"]
    if acct.queue:
        lines.append(f"#SBATCH -p {shlex.quote(acct.queue)}")
    lines.append("#SBATCH -N 1")
    lines.append(f"#SBATCH --ntasks={acct.cpus}")
    lines.append("#SBATCH -o slurm-job.log")
    lines.append("set -e")
    for s in acct.sources:
        lines.append(f"source {s}")
    lines.append("set +e")
    lines.append("ulimit -s unlimited")
    quoted = acct.command.replace("'", "'\\''")
    quoted = quoted.replace("{nproc}", str(acct.cpus))
    # eval 与 echo 都在 cd task 之后, 重定向用本目录相对路径
    lines.append(f"(cd task && eval '{quoted}' > task.log 2>&1; echo $? > {EXIT_FLAG})")
    lines.append(f"touch {DONE_FLAG}")
    return "\n".join(lines) + "\n"


def stage_dir(task_dir, incar_patch):
    """把任务目录暂存并按需给 INCAR 打补丁, 返回暂存路径(用后删除)."""
    tmp = Path(task_dir) / ".staging"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for f in Path(task_dir).iterdir():
        if f.is_file() and not f.name.startswith(".") and f.name != "OUTCAR":
            shutil.copy2(f, tmp / f.name)
    if incar_patch:
        incar = tmp / "INCAR"
        if incar.is_file():
            lines = []
            for line in incar.read_text().split("\n"):
                for key, val in incar_patch.items():
                    if line.strip().startswith(key):
                        # 保留行内注释, 只替换键值
                        comment = ""
                        if "#" in line:
                            line, comment = line.split("#", 1)
                            comment = "#" + comment
                        line = f"{key:<16}= {val} "
                        line += comment if comment else ""
                        break
                lines.append(line)
            incar.write_text("\n".join(lines))
    return tmp


def remote_run(acct, task_dir, tag):
    """在账号上跑一个 VASP 任务, 成功返回 True(OUTCAR 已回传)."""
    job_dir = f"{acct.root}/jobs/{tag}"
    staging = stage_dir(task_dir, acct.incar_patch)
    try:
        if not upload(acct, staging, job_dir + "/task"):
            return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    script = job_script(acct, tag, job_dir)
    ret, out, err = acct.run(
        f"mkdir -p {shlex.quote(job_dir)} && printf %s {shlex.quote(script)} > "
        f"{shlex.quote(job_dir + '/job.slurm')} && "
        f"sbatch {shlex.quote(job_dir + '/job.slurm')}")
    if ret != 0:
        print(f"[fp_dispatch] sbatch 失败({acct.name}): {err.strip()[:200]}",
              )
        return False
    job_id = next((t for t in out.split() if t.isdigit()), None)
    if job_id is None:
        return False
    print(f"[fp_dispatch] {tag} -> {acct.name} job {job_id}", )
    t0 = time.time()
    missing = 0
    while time.time() - t0 < JOB_TIMEOUT_SEC:
        time.sleep(POLL_SEC)
        ret, out, _ = acct.run(f"squeue -h -j {shlex.quote(job_id)} -o %T")
        if ret == 0 and out.strip():
            missing = 0
            continue
        # 不在队列: 可能已完成, 也可能入队延迟(前 90s 不判丢)
        ret, out, _ = acct.run(
            f"test -f {shlex.quote(job_dir + '/' + DONE_FLAG)} && echo Y || echo N")
        if out.strip() == "Y":
            ret, out, _ = acct.run(
                f"cat {shlex.quote(job_dir + '/task/' + EXIT_FLAG)} 2>/dev/null")
            code = out.strip() or "1"
            ok = download(acct, job_dir, task_dir)
            acct.run(f"rm -rf {shlex.quote(job_dir)}")
            print(f"[fp_dispatch] {tag} job {job_id} 完成 exit={code} "
                  f"回传={'OK' if ok else '失败'}", )
            record(task_dir, "remote", acct.name, job_id, code,
                   time.time() - t0)
            return ok and code == "0"
        missing += 1
        if time.time() - t0 > 90 and missing >= 3:
            ret, out, _ = acct.run(
                f"cat {shlex.quote(job_dir + '/slurm-job.log')} "
                f"{shlex.quote(job_dir + '/task/task.log')} 2>/dev/null | tail -5",
                timeout=30)
            if out.strip():
                print(f"[fp_dispatch] 作业现场日志: {out.strip()[-400:]}",
                      )
            print(f"[fp_dispatch] {tag} job {job_id} 丢失", )
            acct.run(f"rm -rf {shlex.quote(job_dir)}")
            return False
    acct.run(f"scancel {shlex.quote(job_id)}")
    acct.run(f"rm -rf {shlex.quote(job_dir)}")
    print(f"[fp_dispatch] {tag} 超时取消", )
    return False


def record(task_dir, mode, detail, job_id="", code="", elapsed=0):
    """记录任务归属: stdout(进 fp.log 随任务回拷) + 聚合 JSONL(脚本目录, 永存)."""
    line = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": Path(task_dir).resolve().name,
        "mode": mode,            # remote / local
        "account": detail,       # username@host 或 local
        "job_id": str(job_id),
        "exit_code": str(code),
        "elapsed_sec": int(elapsed),
    }
    print(f"[fp_dispatch] RECORD {json.dumps(line, ensure_ascii=False)}")
    try:
        logf = Path(__file__).resolve().parent / "fp_dispatch_routes.log"
        with open(logf, "a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


def local_fallback(task_dir, cfg):
    cmd = cfg.get("local_command", "bash fp_wrapper.sh")
    print(f"[fp_dispatch] 本地兜底: {cmd}", )
    t0 = time.time()
    ret = subprocess.run(["bash", "-c", cmd], cwd=task_dir).returncode
    if ret == 0 and (Path(task_dir) / "OUTCAR").is_file():
        record(task_dir, "local", "local", "", "0", time.time() - t0)
    return ret == 0


def main():
    task_dir = Path.cwd()
    here = Path(__file__).resolve().parent
    cfg = json.loads((here / "accounts.json").read_text())
    max_local = int(cfg.get("local_max_concurrent", 2))

    if (task_dir / "OUTCAR").is_file() and (task_dir / "OUTCAR").stat().st_size > 0:
        print("[fp_dispatch] OUTCAR 已存在, 跳过")
        return 0

    accounts = [Account(c) for c in cfg["accounts"]]
    tag = f"{int(time.time())}-{os.getpid()}"

    # 主循环: 集群有空位上集群; 本地有空槽走本地; 都满则等待重试
    while True:
        order = list(range(len(accounts)))
        random.shuffle(order)
        for idx in order:
            acct = accounts[idx]
            if not acct.enabled:
                continue
            used = acct.remote_used()
            if used is not None and used >= acct.max_jobs:
                continue
            for s in range(acct.max_jobs):
                slot = Slot(acct, s)
                if not slot.acquire():
                    continue
                try:
                    used = acct.remote_used()
                    if used is None or used >= acct.max_jobs:
                        break
                    if remote_run(acct, task_dir, tag):
                        return 0
                    if ((task_dir / "OUTCAR").is_file()
                            and (task_dir / "OUTCAR").stat().st_size > 0):
                        return 0
                finally:
                    slot.release()
                break
        # 集群无空位: 尝试本地槽(有并发上限, 防止 10 个 VASP 挤爆 24 核)
        local_acct = Account({"username": "local", "host": "localhost",
                              "private_key_file": "/dev/null",
                              "remote_root": "/tmp", "max_jobs": max_local})
        for s in range(max_local):
            slot = Slot(local_acct, s)
            if not slot.acquire():
                continue
            try:
                if local_fallback(task_dir, cfg):
                    return 0
                print("[fp_dispatch] 本地执行失败", )
                return 1
            finally:
                slot.release()
        # 集群与本地均满: 等待一个周期后重新探测(集群空位会被再次优先利用)
        print(f"[fp_dispatch] 集群与本地均满载, {POLL_SEC}s 后重试")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    sys.exit(main())
