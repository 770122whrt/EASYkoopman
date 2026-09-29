"""Bounded independent failed-prefix audit; exit zero means NO_GO classified."""
import argparse
import gzip
import json
from pathlib import Path
import sys

def main():
    p=argparse.ArgumentParser();p.add_argument('--release-root',type=Path,required=True);p.add_argument('--case',required=True)
    args=p.parse_args();sys.path.insert(0,str(args.release_root))
    addon=Path(__file__).resolve().parents[1]
    import workflows,koopman
    for package in (workflows,koopman):package.__path__=[str(addon/package.__name__),*list(package.__path__)]
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    from workflows.validate_support_failure_v68 import validate_failure
    case=next(q for q in json.loads((addon/'protocol.json').read_text())['cases'] if q['case_id']==args.case)
    folder=addon/'results'/case['case_id']
    with gzip.open(folder/'output/diagnostic.json.gz','rt') as f:data=json.load(f)
    assets=load_assets(AssetLocation(str(args.release_root),'.','assets/v38/inputs',HANDOFF_SHA),model_key=case['model_key'])
    result=validate_failure(data,case,assets.domains[case['configuration']],assets.context(case['configuration']))
    with (folder/'failure-analysis.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
