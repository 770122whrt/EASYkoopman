"""Read-only numerical platform probe; not a trajectory acceptance or simulation."""
import argparse
import gzip
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import torch
from workflows.control_seam_v23 import ControlKernel


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    raw=a.trace.read_bytes();d=json.loads(gzip.decompress(raw));cfg=d['case']['configuration']
    k=ControlKernel(cfg);commands=[i['decision']['packet']['command'] for i in d['intervals']]
    commands.extend(u for s in d['solve_audit'] for u in s['commands'])
    result=dict(scope='platform_allocation_diagnostic_only',trace_sha256=hashlib.sha256(raw).hexdigest(),
        platform=platform.platform(),python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,
        torch_threads=torch.get_num_threads(),configuration=cfg,wrench_matrix=k.B.tolist(),commands=commands,
        allocations=[{key:value.tolist() for key,value in k.command(u,pre_tam=True).items()} for u in commands])
    a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps({key:value for key,value in result.items() if key not in ('wrench_matrix','commands','allocations')}))


if __name__=='__main__':main()
