"""Require fresh prediction and solver evidence before the two-second comparison."""
import json
from pathlib import Path
import sys


def verify_control_gate(model_sha,kind,validation,test,solver):
    for role,path in [('validation',validation),('test',test)]:
        r=json.loads(Path(path).read_text(encoding='utf8'))
        if (r.get('schema')!='v86-prediction-evaluation' or r['role']!=role
                or r['model_sha256']!=model_sha or not r['gates'][kind]['prediction_passed']
                or r['model_fits']!=0):raise ValueError('v86_prediction_gate:'+role)
    r=json.loads(Path(solver).read_text(encoding='utf8'))
    if (r.get('schema')!='v86-offline-solver-validation' or r['model_sha256']!=model_sha
            or not r['arms'][kind]['passed']):raise ValueError('v86_solver_gate')


if __name__=='__main__':
    from workflows.collect_learned_v82 import main
    sys.exit(main(experiment='v86'))
