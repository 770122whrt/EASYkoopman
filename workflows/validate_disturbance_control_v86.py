"""Reuse full native, causal, geometry, actuator and decision acceptance for v86."""
import argparse
import gzip
import json
from pathlib import Path
from workflows.validate_learned_v82 import validate
from workflows.runtime_assets_v56 import AssetLocation,load_assets
from workflows.fit_disturbance_v86 import write_new


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('trace','assets','learned-model','learned-sha256','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--native-exit',type=int,required=True);a=p.parse_args()
    assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    with gzip.open(a.trace,'rt',encoding='utf8') as f:data=json.load(f)
    result=validate(data,assets,a.native_exit,learned_model=a.learned_model,
        learned_sha256=a.learned_sha256,experiment='v86')
    write_new(a.output,result)
