"""Fixed base, two excitation fits and one held excitation; no target selection.

Ten predeclared candidates, same old nonlinear lift, constant mechanical context.
Historical-data diagnosis only. No ordinary raw-state linear model or control run.
"""
import hashlib
import json
from pathlib import Path
import time
from workflows.calibrate_lifted_v84 import GRID, fit as fit_fixed
from workflows.calibrate_bilinear_v85 import fit as fit_bilinear
from koopman.lifted_propagation_v84 import prepare_lifted
from koopman.bilinear_lifted_v85 import prepare_bilinear
from workflows.compare_models_v84 import evaluate, prediction_gate, GATE
from workflows.fit_learned_velocity_v81 import aggregate, ORIGINS, HORIZONS
from workflows.identify_sparse_world_v30 import load_fit_cache

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/evidence/phase9/single-configuration-v85-20260927'


def split_base(episodes):
    base = [e for e in episodes if e.case['configuration'] == 'base']
    if len(base) != 3 or {e.case['excitation'] for e in base} != {'prbs','multisine','chirp'}:
        raise ValueError('base_excitation_inventory')
    by = {e.case['excitation']:e for e in base}
    training, heldout = [by['prbs'],by['multisine']], [by['chirp']]
    if {e.trace_sha256 for e in training} & {e.trace_sha256 for e in heldout}:
        raise ValueError('base_excitation_overlap')
    return training, heldout


def run():
    started=time.monotonic(); OUT.mkdir(parents=True,exist_ok=False)
    def check():
        if time.monotonic()-started > 120: raise TimeoutError('single_configuration_120_seconds')
    def write(name,value):
        payload=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
        if sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())+len(payload)>64*1024**2:
            raise RuntimeError('single_configuration_64_mib')
        with (OUT/name).open('xb') as f: f.write(payload)
    sources=[Path(__file__),ROOT/'koopman/lifted_propagation_v84.py',
        ROOT/'koopman/bilinear_lifted_v85.py',ROOT/'workflows/calibrate_lifted_v84.py',
        ROOT/'workflows/calibrate_bilinear_v85.py',ROOT/'workflows/compare_models_v84.py']
    protocol=dict(schema='single-configuration-lifted-diagnosis-v85',configuration='base',
        training_excitations=['prbs','multisine'],heldout_excitation='chirp',ridge_grid=list(GRID),
        selection='none; report every predeclared candidate; heldout never selects a deployment model',
        nonlinear_lift_changed=False,context='one constant mechanical context, no cross-configuration inference',
        maximum_seconds=120,maximum_bytes=64*1024**2,maximum_new_fits=10,
        origins=list(ORIGINS),horizons=list(HORIZONS),gate=GATE,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        blind_test=False,physics_runs=0,solver_runs=0)
    write('protocol.json',protocol) # Before data fitting, same error budget as v84.
    train,held=split_base(load_fit_cache(ROOT))
    write('split.json',dict(training={e.case['run_id']:e.trace_sha256 for e in train},
        heldout={e.case['run_id']:e.trace_sha256 for e in held}))
    training_rows=[];heldout_rows=[];gates={}
    for family,fit,prepare in [('LK',fit_fixed,prepare_lifted),('BLK',fit_bilinear,prepare_bilinear)]:
        for ridge in GRID:
            check();name=f'{family}_{ridge:g}';record=fit(train,ridge);check()
            if any(record['context_varying']):raise ValueError('single_context_must_be_constant')
            write(name+'__model.json',record)
            builder={name:lambda c,r=record,p=prepare:p(r,c)}
            tr=evaluate(train,builder);hr=evaluate(held,builder);check()
            training_rows.extend(tr);heldout_rows.extend(hr)
            gates[name]=dict(training=prediction_gate(tr),heldout=prediction_gate(hr))
            write(name+'__evaluation.json',dict(training_rows=tr,heldout_rows=hr,gates=gates[name]))
            print(json.dumps(dict(model=name,**gates[name])),flush=True)
    persistent=evaluate(held,{'persistence':lambda c:lambda x,u,c:x.copy()})
    heldout_rows.extend(persistent)
    result=dict(status='completed_single_configuration_retrospective_diagnosis',protocol=protocol,
        elapsed_seconds=time.monotonic()-started,model_fits=10,training_summary=aggregate(training_rows),
        heldout_summary=aggregate(heldout_rows),gates=gates,selected_model=None,
        control_admitted=False,cross_configuration_generalization_claimed=False)
    write('report.json',result)


if __name__=='__main__':run()
