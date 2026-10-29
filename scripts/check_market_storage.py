#!/usr/bin/env python3
"""Trusted Q17 offline synthetic verifier; accepts only a pinned wheel path."""
import sys
if __name__ == "__main__" and (not sys.flags.isolated or not sys.flags.no_site):
    sys.stdout.write('{"result":"fail","reason":"isolated_python_required"}\n')
    raise SystemExit(2)

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from quantharbor.runtime.isolation import _bounded_process

IMAGE = "python@sha256:608b27b2db85abf38d81685085cd1166a5ed7ada66549f0dfe53a75bb830cd5d"
WHEEL = "pyarrow-26.0.0-cp313-cp313-manylinux_2_28_aarch64.whl"
WHEEL_HASH = "e3b190ba1d3d22a5a8758597f797111b77d433473744352a184a5ee0a42d672e"
SCOPE = "synthetic-market-storage-v1"


class CheckFailure(Exception):
    pass


def regular_bytes(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise CheckFailure("input_file_boundary")
        with os.fdopen(os.dup(fd), "rb") as stream:
            value = stream.read(limit + 1)
        after = os.fstat(fd)
        if len(value) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise CheckFailure("input_changed")
        return value
    finally:
        os.close(fd)


def build_context(target, wheel):
    # Resolve public Git candidates before opening any source content. Never walk private trees.
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_quality
    required = {"containers/Dockerfile.market-storage", "containers/requirements.market-storage.txt",
                "config/runtime.synthetic.toml", "config/runtime-lock.json", "config/market-storage-lock.json",
                "pyproject.toml"}
    names, ignored = check_quality.candidates(ROOT)
    files = set()
    for name in names:
        if name in ignored:
            continue
        if name in required or (name.endswith(".py") and name.startswith(
                ("src/quantharbor/", "tests/product/", "tests/storage/"))):
            check_quality.classify(name)
            files.add(name)
    if not required <= files:
        raise CheckFailure("public_context_incomplete")
    total = 0
    root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for name in sorted(files):
            data, _ = check_quality._read_public(root_fd, name)
            total += len(data)
            if total > 16777216:
                raise CheckFailure("context_limit")
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
    finally:
        os.close(root_fd)
    (target / "wheels").mkdir()
    (target / "wheels" / WHEEL).write_bytes(wheel)


PROGRAM = '''import json,sys,unittest,subprocess,tempfile,os,stat
from pathlib import Path
sys.path.insert(0,"/app/src")
import pyarrow as pa
from importlib.metadata import distribution
import hashlib
dist=distribution('pyarrow')
assert not dist.requires
for suffix,expected in (('licenses/LICENSE.txt','cd03925a27219d326d622609fbcae6567279af8b8885c33d5969a9e4ef5d7525'),('licenses/NOTICE.txt','afd895d61a00101f6d5a41cf518c83865d815e8109e956f512a0ce4ea9738c06')):
    paths=[p for p in dist.files if str(p).endswith(suffix)]
    assert len(paths)==1 and hashlib.sha256(dist.locate_file(paths[0]).read_bytes()).hexdigest()==expected
assert pa.__version__ == "26.0.0" and sys.version_info[:3] == (3,13,17)
assert pa.decimal128(38,18).precision == 38
store=os.stat('/store')
assert store.st_uid == os.getuid() == 10001 and stat.S_IMODE(store.st_mode)==0o700
assert tempfile.gettempdir() == '/store'
assert os.stat('/store').st_dev != os.stat('/tmp').st_dev
with tempfile.TemporaryDirectory(prefix="qh-arrow-") as d:
    path=str(Path(d)/"probe.parquet")
    writer="""from decimal import Decimal
from datetime import datetime,timezone
import sys,pyarrow as pa,pyarrow.parquet as pq
s=pa.schema([pa.field('value',pa.decimal128(38,18),nullable=False),pa.field('at',pa.timestamp('us',tz='UTC'),nullable=False)])
t=pa.Table.from_pylist([{'value':Decimal('123.000000000000000001'),'at':datetime(2024,1,1,0,0,0,123456,tzinfo=timezone.utc)}],schema=s)
t.validate(full=True)
pq.write_table(t,sys.argv[1],compression='NONE',version='2.6',allow_truncated_timestamps=False,write_page_checksum=True)
"""
    reader="""from decimal import Decimal
from datetime import datetime,timezone
import sys,pyarrow as pa,pyarrow.parquet as pq
with open(sys.argv[1],'rb') as f:
 p=pq.ParquetFile(f,pre_buffer=False,arrow_extensions_enabled=False,page_checksum_verification=True,thrift_string_size_limit=65536,thrift_container_size_limit=65536,schema_depth_limit=8)
 t=p.read(use_threads=False); t.validate(full=True)
 assert t.schema.field('value').type == pa.decimal128(38,18)
 assert t.schema.field('at').type == pa.timestamp('us',tz='UTC')
 row=t.to_pylist()[0]
 assert row['value'] == Decimal('123.000000000000000001')
 assert row['at'] == datetime(2024,1,1,0,0,0,123456,tzinfo=timezone.utc)
"""
    subprocess.run([sys.executable,'-I','-c',writer,path],check=True,timeout=20)
    subprocess.run([sys.executable,'-I','-c',reader,path],check=True,timeout=20)
counts={}
for name,minimum in (('product',104),('storage',1)):
    suite=unittest.defaultTestLoader.discover('/app/tests/'+name)
    count=suite.countTestCases()
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    assert count>=minimum and result.testsRun==count and not result.skipped and result.wasSuccessful()
    counts[name]=count
print(json.dumps({'runtime':'3.13.17','pyarrow':'26.0.0','decimal_timestamp_new_process':True,'storage_medium':'own_local_docker_volume','tests':counts}))
'''


def main():
    report = {"scope": SCOPE, "result": "fail", "cleanup": "not_created"}
    if len(sys.argv) != 3 or sys.argv[1] != "--wheel":
        print(json.dumps(report | {"reason": "pinned_wheel_argument_required"}))
        return 2
    env = {key: os.environ[key] for key in ("PATH", "TMPDIR") if key in os.environ}
    discovery = env | {key: os.environ[key] for key in ("HOME", "DOCKER_CONFIG") if key in os.environ}
    token = uuid.uuid4().hex
    name = "qh-market-" + token
    volume = "qh-market-data-" + token
    tag = "qh-market-check:" + token
    labels = {"quantharbor.scope": SCOPE, "quantharbor.run": token}
    started = time.monotonic()
    stage = "inputs"
    created = built = volume_created = False
    base = None

    def run(args, *, environment=None, timeout=10):
        result = _bounded_process(args, env=environment or env, timeout=timeout, output_limit=1048576)
        if result.limit or result.returncode != 0:
            raise CheckFailure("command_failed_" + stage)
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="qh-market-build-") as private:
        directory = Path(private)
        try:
            if Path(sys.argv[2]).name != WHEEL:
                raise CheckFailure("wheel_name_mismatch")
            wheel = regular_bytes(Path(sys.argv[2]), 50865064)
            if len(wheel) != 50865064 or hashlib.sha256(wheel).hexdigest() != WHEEL_HASH:
                raise CheckFailure("wheel_integrity")
            binary = shutil.which("docker")
            if binary is None:
                raise CheckFailure("docker_unavailable")
            lock = json.loads(regular_bytes(ROOT / "config/market-storage-lock.json", 65536))
            if (lock["wheel_sha256"], lock["wheel"], lock["python_image"], lock["platform"]) != (
                    WHEEL_HASH, WHEEL, IMAGE, "linux/arm64"):
                raise CheckFailure("lock_mismatch")
            context = run([binary,"context","show"],environment=discovery).decode().strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}",context):
                raise CheckFailure("context_invalid")
            endpoint = json.loads(run([binary,"context","inspect","--format","{{json .Endpoints.docker.Host}}",context],environment=discovery))
            if type(endpoint) is not str or not endpoint.startswith("unix:///") or any(ord(x)<32 for x in endpoint):
                raise CheckFailure("nonlocal_endpoint")
            base = [binary,"--host",endpoint]
            for child in ("home","docker","buildx","context"):
                (directory/child).mkdir(mode=0o700)
            env.update(HOME=str(directory/"home"),DOCKER_CONFIG=str(directory/"docker"),BUILDX_CONFIG=str(directory/"buildx"))
            run(base+["image","inspect","--format","{{.Id}}",IMAGE])
            build_context(directory/"context",wheel)
            sys.path.insert(0,str(ROOT/"scripts"))
            import check_quality
            checked = {}
            for item in ("config/market-storage-lock.json", "containers/Dockerfile.market-storage", "containers/requirements.market-storage.txt"):
                content = regular_bytes(directory/"context"/item,1048576)
                checked[item] = (content,content.decode("utf-8"))
            if check_quality.check_market_storage(checked):
                raise CheckFailure("storage_build_policy_drift")
            stage = "offline_build"
            built = True
            run(base+["build","--network=none","--pull=false","--platform=linux/arm64","--label","quantharbor.scope="+SCOPE,"--label","quantharbor.run="+token,"-t",tag,"-f",str(directory/"context/containers/Dockerfile.market-storage"),str(directory/"context")],timeout=120)
            built = True
            stage = "volume_create"
            volume_created = True
            run(base+["volume","create","--driver","local","--label","quantharbor.scope="+SCOPE,
                      "--label","quantharbor.run="+token,volume])
            v = json.loads(run(base+["volume","inspect",volume]))[0]
            if v["Name"] != volume or v["Driver"] != "local" or v["Options"] or v["Labels"] != labels:
                raise CheckFailure("volume_boundary")
            stage = "container_create"
            created = True
            run(base+["create","--pull=never","--platform=linux/arm64","--name",name,
                "--label","quantharbor.scope="+SCOPE,"--label","quantharbor.run="+token,
                "--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges=true",
                "--memory=512m","--memory-swap=512m","--cpus=1","--pids-limit=64","--ipc=none",
                "--log-driver=none","--tmpfs","/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777",
                "--mount","type=volume,src="+volume+",dst=/store","--env","TMPDIR=/store",
                "--user=10001:10001",tag,"python","-I","-u","-c",PROGRAM])
            created = True
            stage = "container_inspect"
            obj = json.loads(run(base+["inspect",name]))[0]
            hc = obj["HostConfig"]
            mounts = obj["Mounts"]
            if (len(mounts) != 1 or mounts[0]["Type"] != "volume" or mounts[0]["Name"] != volume
                    or mounts[0]["Destination"] != "/store" or mounts[0]["Driver"] != "local"
                    or mounts[0]["RW"] is not True):
                raise CheckFailure("mount_boundary")
            if (obj["Config"]["Labels"] != labels or hc["NetworkMode"] != "none"
                    or not hc["ReadonlyRootfs"] or hc["Memory"] != 536870912
                    or obj["Config"]["User"] != "10001:10001" or hc["CapDrop"] != ["ALL"]
                    or hc["Binds"] or hc["Privileged"] or hc["PidMode"] or hc["IpcMode"] != "none"):
                raise CheckFailure("container_boundary")
            expected_env = json.loads(run(base+["image","inspect","--format","{{json .Config.Env}}",IMAGE]))
            expected_env = dict(entry.split("=",1) for entry in expected_env)
            expected_env.update(PYTHONPATH="/app/src",PYTHONDONTWRITEBYTECODE="1",PYTHONUNBUFFERED="1",TMPDIR="/store")
            actual_entries = obj["Config"]["Env"]
            actual_env = dict(entry.split("=",1) for entry in actual_entries)
            if (actual_env != expected_env or len(actual_env) != len(actual_entries)
                    or hc["MemorySwap"] != 536870912 or hc["NanoCpus"] != 1000000000
                    or hc["PidsLimit"] != 64 or hc["SecurityOpt"] != ["no-new-privileges=true"]
                    or hc["Tmpfs"] != {"/tmp":"rw,noexec,nosuid,nodev,size=67108864,mode=1777"}
                    or hc["LogConfig"]["Type"] != "none"):
                raise CheckFailure("container_environment_or_limits")
            stage = "synthetic_tests"
            data = run(base+["start","--attach",name],timeout=90)
            state = json.loads(run(base+["inspect","--format","{{json .State}}",name]))
            if state["Running"] or state["ExitCode"] != 0 or state["Status"] != "exited":
                raise CheckFailure("container_exit")
            report.update(json.loads(data))
            report["result"] = "pass"
        except Exception as error:
            report["reason"] = str(error) if type(error) is CheckFailure else "verification_failed_"+stage
        finally:
            try:
                if created:
                    owned = json.loads(run(base+["inspect","--format","{{json .Config.Labels}}",name]))
                    if owned != labels:
                        raise CheckFailure("ownership_mismatch")
                    run(base+["rm","-f",name])
                if volume_created:
                    owned = json.loads(run(base+["volume","inspect","--format","{{json .Labels}}",volume]))
                    if owned != labels:
                        raise CheckFailure("volume_ownership_mismatch")
                    run(base+["volume","rm",volume])
                if built:
                    owned = json.loads(run(base+["image","inspect","--format","{{json .Config.Labels}}",tag]))
                    if owned != labels:
                        raise CheckFailure("image_ownership_mismatch")
                    run(base+["image","rm",tag])
                if base is not None and (created or built or volume_created):
                    if run(base+["ps","-a","--filter","label=quantharbor.run="+token,"-q"]).strip():
                        raise CheckFailure("container_cleanup_unconfirmed")
                    if run(base+["image","ls","--filter","label=quantharbor.run="+token,"-q"]).strip():
                        raise CheckFailure("image_cleanup_unconfirmed")
                    if run(base+["volume","ls","--filter","label=quantharbor.run="+token,"-q"]).strip():
                        raise CheckFailure("volume_cleanup_unconfirmed")
                report["cleanup"] = "own_objects_removed" if created or built or volume_created else "not_created"
            except Exception:
                report["result"] = "fail"
                report["cleanup"] = "unconfirmed"
    report["seconds"] = round(time.monotonic()-started,3)
    print(json.dumps(report,sort_keys=True))
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
