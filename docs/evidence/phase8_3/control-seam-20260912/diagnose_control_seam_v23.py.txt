"""Fixed CPU component interventions; no archived dataset or model fitting."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workflows.control_seam_v23 import ControlKernel,estimate_speed
from koopman.diagnostics_v23 import reserve_output,json_safe
from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS,qualification_record


def run(run_id):
    out=reserve_output(ROOT/'docs/evidence/phase8_3',run_id)
    paths=[Path(__file__),ROOT/'workflows/control_seam_v23.py',ROOT/'easyuuv_nc/env/easyuuv_env.py',
        ROOT/'easyuuv_nc/env/thruster_dynamics.py',ROOT/'easyuuv_nc/thrust_allocation.py',ROOT/'easyuuv_nc/embodiments.py',
        ROOT/'.planning/phases/08.3-control-identification-forensics/08.3-02-PLAN.md']
    r={'status':'started','evidence_level':'local_actual_control_kernels_no_isaac_no_hull_integration',
       'new_dataset_opens':0,'model_fits':0,'model_handoff':False,
       'settings':{'physics_dt':1/120,'decimation':2,'amplitude':.1,'intervals':32,'step_index':8,'prbs_hold':4,'seed':8201},
       'sources_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
       'calibration':{},'temporal_probes':[],'reset_alias':{},'geometry':{}}
    for p in paths:(out/(p.name+'.txt')).write_bytes(p.read_bytes())
    def save():(out/'report.json').write_text(json.dumps(json_safe(r),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    save()
    try:
        Bs={}
        for c in SUPPORTED_EMBODIMENTS:
            r['calibration'][c]={};mask=qualification_record(c)['control_mask'];Bs[c]=ControlKernel(c).B.numpy()
            for j,axis in enumerate(('roll','pitch','yaw','depth')):
                k=ControlKernel(c);u=np.zeros(4);u[j]=.1
                a=k.command(u,pre_tam=True);f=k.advance(a['pwm']);g=k.advance(a['pwm'])
                r['calibration'][c][axis]={'requested_pre_tam':u,'effective_pre_tam':a['virtual_control'],
                    'raw_pwm':a['pwm_raw'],'clipped_pwm':a['pwm'],'B_times_raw_pwm':k.B.numpy()@a['pwm_raw'],
                    'first_substep':f,'second_substep':g,'thruster_impulse_6':(f['wrench']+g['wrench'])/120}
                for excitation in ['step','prbs']:
                    raw=np.zeros((32,4))
                    if excitation=='step':raw[8:,j]=.1
                    else:raw[:,j]=np.repeat(np.random.default_rng(8201).choice([-.1,.1],8),4)
                    raw*=np.asarray(mask)
                    actual,held=ControlKernel(c),ControlKernel(c)
                    estimate=np.zeros(actual.B.shape[1]);max_est=0.;records=[];wa=[];wh=[];deltas=[];sat=0
                    for i,command in enumerate(raw):
                        pair=[]
                        for _ in range(2):
                            cmd=actual.command(command);obs=actual.advance(cmd['pwm'])
                            estimate=estimate_speed(estimate,cmd['pwm'],tau=actual.tau,dt=actual.dt)
                            max_est=max(max_est,float(np.max(np.abs(estimate-obs['speed']))))
                            pair.append({'command':cmd,'actuator':obs});sat+=int(np.count_nonzero(np.abs(cmd['pwm_raw'])>1))
                        alternate=[held.advance(pair[-1]['command']['pwm']) for _ in range(2)]
                        wa.extend(p['actuator']['wrench'] for p in pair);wh.extend(p['wrench'] for p in alternate)
                        deltas.append(pair[0]['command']['virtual_control']-pair[1]['command']['virtual_control'])
                        records.append({'interval':i,'raw_action':command,'ordered':pair,'held_last':alternate})
                    wa,wh=np.asarray(wa),np.asarray(wh)
                    discrepancy=np.sum(np.abs(wa-wh),axis=0)/120;reference=np.sum(np.abs(wa),axis=0)/120
                    r['temporal_probes'].append({'configuration':c,'axis':axis,'excitation':excitation,
                        'max_substep_control_difference_4':np.max(np.abs(deltas),axis=0),
                        'wrench_l1_impulse_difference_6':discrepancy,'ordered_wrench_l1_impulse_6':reference,
                        'relative_l1_difference_6':[float(a/b) if b>1e-12 else None for a,b in zip(discrepancy,reference)],
                        'max_estimated_speed_error':max_est,'clipped_motor_substeps':sat,'records':records})
            alias=[]
            for sign in [-1,1]:
                k=ControlKernel(c);k.env.old_actions[0,3]=sign*.1
                proxy=ActuatorMemoryProxyV21.from_validated_state(k.tau,1/60,mask,np.zeros(4))
                before=proxy.current().copy();first=k.command(np.zeros(4));f=k.advance(first['pwm'])
                last=k.command(np.zeros(4));g=k.advance(last['pwm']);proxy.advance(last['virtual_control'])
                alias.append({'previous_action_depth':sign*.1,'memory_before':before,'memory_after':proxy.current(),
                    'recorded_last_virtual_control':last['virtual_control'],'first_command':first,'first_actuator':f,'last_actuator':g})
            r['reset_alias'][c]={'conditions':alias,'recorded_inputs_equal':bool(np.array_equal(alias[0]['memory_before'],alias[1]['memory_before']) and np.array_equal(alias[0]['recorded_last_virtual_control'],alias[1]['recorded_last_virtual_control'])),
                'last_wrench_difference_6':alias[0]['last_actuator']['wrench']-alias[1]['last_actuator']['wrench']}
            save();print(c,'complete',flush=True)
        r['geometry']={'uuv4_vs_uuv4_angled_max_abs_B_difference':np.max(np.abs(Bs['uuv4']-Bs['uuv4_angled'])),
            'uuv6_vs_uuv6_angled_max_abs_B_difference':np.max(np.abs(Bs['uuv6']-Bs['uuv6_angled']))}
        r['status']='completed_local_control_subsystem_assay';save()
    except Exception as exc:
        r['status']='failed';r['exception']=str(exc);save();raise
    print(out,flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-id',required=True)
    run(parser.parse_args().run_id)
