"""Measured-state recovery baseline and frozen-model worker integration.

Only the explicit prefix is committed by the parent. The tail is a proposed
slew-limited ramp toward ONE demand from the measured request state, not future
closed-loop feedback. No object here issues commands or authenticates execution.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import numpy as np

from koopman.bounded_feedback_v46 import FeedbackConfig, feedback_demand
from koopman.bounded_feedback_v47 import PreparedTrackingMap, limit_tracking_command
from koopman.bounded_mpc_v44 import COMMAND_ATOL, SearchConfig, SupportDomain, owned
from koopman.bounded_mpc_v45 import BoundedMPC
from koopman.control_objective_v44 import ObjectiveWeights, checked_reference
from koopman.execution_ledger_v48 import ExecutionCapture
from koopman.prepared_projected_v40 import _context_key
from koopman.prepared_commands_v45 import check_deadline


@dataclass(frozen=True)
class PlanningRequest:
    request_id: str
    capture: ExecutionCapture
    prefix: np.ndarray

    def __post_init__(self):
        c=self.capture;p=np.asarray(self.prefix,dtype=np.float32)
        if (not isinstance(c,ExecutionCapture) or not isinstance(self.request_id,str)
                or not self.request_id.strip() or len(self.request_id)>256
                or type(c.physics_index) is not int or c.physics_index<2 or c.physics_index%2
                or c.previous is None or type(c.reference_revision) is not int or c.reference_revision<0
                or type(c.worker_generation) is not int or c.worker_generation<0
                or not isinstance(c.history_digest,str) or not re.fullmatch('[0-9a-f]{64}',c.history_digest)
                or p.ndim!=2 or p.shape[1]!=4 or not 1<=len(p)<128 or not np.isfinite(p).all()):
            raise ValueError('planning_request_invalid_or_startup_unconfirmed')
        if any(not isinstance(v,str) or not v.strip() for v in
               (c.execution_id,c.episode_id,c.reset_id,c.reference_id)):
            raise ValueError('planning_request_identity')
        object.__setattr__(self,'capture',deepcopy(c))
        object.__setattr__(self,'prefix',owned(p,np.float32))


def request_binding(request):
    c=request.capture
    return dict(request_id=request.request_id,execution_id=c.execution_id,episode_id=c.episode_id,
        reset_id=c.reset_id,history_digest=c.history_digest,worker_generation=c.worker_generation,
        reference_id=c.reference_id,reference_revision=c.reference_revision,configuration=c.configuration,
        context_key=list(c.context_key),model_id=c.model_id,support_id=c.support_id,
        origin_control=c.physics_index//2,physics_index=c.physics_index,
        activation_control=c.physics_index//2+len(request.prefix),
        prefix_sha256=hashlib.sha256(np.asarray(request.prefix,dtype=np.float32).tobytes()).hexdigest())


class RecoveryBaseline:
    def __init__(self,domain,context,*,config=FeedbackConfig(),allow_diagnostic=False):
        if (not isinstance(domain,SupportDomain) or (not domain._verified_fit and not allow_diagnostic)
                or _context_key(context)!=domain.context_key or not isinstance(config,FeedbackConfig)):
            raise ValueError('recovery_setup_binding')
        self.domain=domain;self.context=replace(context);self.config=config
        self.steady=PreparedTrackingMap(domain.configuration,self.context)

    def build(self,state,reference,previous,prefix,*,horizon,deadline):
        result=dict(status='no_baseline',reason=None,commands=None,tracking=[],requested_wrench=None,
            static_command=None,target_rewritten=False,future_feedback_assumed=False,actual_history_advanced=False)
        def reject(reason):result.update(status='no_baseline',reason=reason,commands=None);return result
        try:
            check_deadline(deadline)
            old=np.array(previous,dtype=float,copy=True);p=np.array(prefix,dtype=np.float32,copy=True)
            x=np.array(state,dtype=float,copy=True);ref=checked_reference(reference)
            if (type(horizon) is not int or not 2<=horizon<=128 or p.ndim!=2 or p.shape[1]!=4
                    or not 1<=len(p)<horizon or old.shape!=(4,) or not np.isfinite(old).all()
                    or not np.isfinite(p).all() or x.shape!=(11,)):
                return reject('recovery_input')
            if self.domain.check_states(x[None]):return reject('recovery_initial_state')
            target=feedback_demand(x,ref,self.domain.configuration,self.context,self.config)['target_wrench']
            result['requested_wrench']=owned(target)
            # Prefix commands have already been chosen by the parent. Never clip
            # or replace them silently to make a prediction feasible.
            commands=[];prior=old
            for u in np.vstack([old,p]):
                check_deadline(deadline)
                record=self.steady.inspect(u,target,self.domain.command_lower,self.domain.command_upper)
                if not record['command_constraints_accepted']:return reject('recovery_prefix_constraints')
                if np.any(np.abs(u-prior)>self.config.slew+COMMAND_ATOL):return reject('recovery_prefix_slew')
                prior=u
            commands.extend(p)
            inverse=self.steady.static_inverse(target,prior,self.config,
                deadline=min(deadline,time.perf_counter()+self.config.timeout_ms/1000))
            if inverse['status']!='ready':return reject('recovery_'+inverse['reason'])
            full=inverse['command'];result['static_command']=owned(full,np.float32)
            for _ in range(horizon-len(p)):
                check_deadline(deadline)
                limited=limit_tracking_command(self.steady,target,full,prior,self.domain.command_lower,
                    self.domain.command_upper,self.config.slew,deadline=deadline)
                if limited['status']!='ready':return reject('recovery_'+limited['reason'])
                prior=limited['command'];commands.append(prior)
                result['tracking'].append(dict(status=limited['tracking_status'],alpha=limited['alpha'],
                    zero_progress=limited['zero_progress'],limitations=limited['limitations'],
                    acceleration_error=owned(limited['inspection']['acceleration_error'])))
            check_deadline(deadline)
            result.update(status='ready',commands=owned(commands,np.float32));return result
        except TimeoutError:return reject('timeout')
        except (ValueError,TypeError,FloatingPointError,np.linalg.LinAlgError) as exc:
            return reject('recovery_invalid:'+str(exc))


class RecoverySolver:
    """Worker callable; parent must still admit identities, prefix and state."""
    def __init__(self,domain,context,predictor,*,config=SearchConfig(),feedback_config=FeedbackConfig(),
                 weights=ObjectiveWeights(),allow_diagnostic=False):
        if any(abs(v-feedback_config.slew)>1e-12 for v in config.slew):
            raise ValueError('recovery_slew_contract_mismatch')
        self.domain=domain;self.config=config
        self.baseline=RecoveryBaseline(domain,context,config=feedback_config,allow_diagnostic=allow_diagnostic)
        self.solver=BoundedMPC(domain,predictor,model_id=domain.model_id,config=config,weights=weights,
            allow_diagnostic=allow_diagnostic)

    def __call__(self,request):
        started=time.perf_counter();deadline=started+self.config.timeout_ms/1000
        result=dict(status='no_plan',reason=None,commands=None,predictions=None,runtime_eligible=False,
                    actual_history_advanced=False,binding=None)
        def reject(reason):
            result.update(status='no_plan',reason=reason,commands=None,predictions=None,
                          elapsed_ms=1000*(time.perf_counter()-started));return result
        try:
            if not isinstance(request,PlanningRequest):return reject('request_type')
            # Revalidate after trusted IPC unpickling; labels alone do not prove
            # a real reset or real execution, which remains the parent's job.
            request=PlanningRequest(request.request_id,request.capture,request.prefix)
            c=request.capture;domain=self.domain;origin=c.origin
            if (c.configuration!=domain.configuration or c.context_key!=domain.context_key
                    or c.model_id!=domain.model_id or c.support_id!=domain.identity
                    or origin._configuration!=domain.configuration or _context_key(origin._context)!=domain.context_key
                    or origin.origin_control*2!=c.physics_index or len(request.prefix)>=self.config.horizon):
                return reject('request_domain_or_origin_binding')
            result['binding']=request_binding(request)
            baseline=self.baseline.build(c.state,c.reference,c.previous,request.prefix,
                horizon=self.config.horizon,deadline=deadline)
            result['recovery']=baseline
            if baseline['status']!='ready':return reject(baseline['reason'])
            check_deadline(deadline)
            # Baseline construction is charged against the same solver deadline.
            self.solver.config=replace(self.config,timeout_ms=1000*(deadline-time.perf_counter()))
            answer=self.solver.solve(origin,c.state,baseline['commands'],c.previous,c.reference,
                episode_id=c.episode_id,reference_id=c.reference_id,request_id=request.request_id,
                committed_prefix=len(request.prefix))
            result.update(answer)
            if answer['status']=='no_plan':return reject(answer['reason'])
            if not np.array_equal(answer['commands'][:len(request.prefix)],request.prefix):
                return reject('selected_prefix_changed')
            # v45 screens raw PWM but not proximity to a deadzone boundary.
            # Reject the whole returned proposal if that extra runtime contract
            # fails; do not relabel another candidate as the selected optimum.
            for u in answer['commands']:
                check_deadline(deadline)
                row=self.baseline.steady.inspect(u,baseline['requested_wrench'],domain.command_lower,domain.command_upper)
                if not row['command_constraints_accepted']:return reject('selected_command_constraints')
            check_deadline(deadline)
            result.update(elapsed_ms=1000*(time.perf_counter()-started),runtime_eligible=False)
            return result
        except TimeoutError:return reject('timeout')
        except (ValueError,TypeError,AttributeError,FloatingPointError) as exc:
            return reject('invalid_request_or_numerical:'+str(exc))


@dataclass(frozen=True)
class FrozenWorkerSpec:
    root: str
    configuration: str
    context: object
    model_key: str
    model_sha256: str
    handoff_sha256: str
    support_id: str
    compiler_directory: object
    config: SearchConfig = SearchConfig()
    feedback_config: FeedbackConfig = FeedbackConfig()


def frozen_model_factory(spec):
    """Load/verify/compile before READY; no fitting, source edits or downloads."""
    if not isinstance(spec,FrozenWorkerSpec):raise ValueError('frozen_worker_spec')
    root=Path(spec.root).resolve()
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    payload=handoff_path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=spec.handoff_sha256:raise ValueError('frozen_worker_handoff_hash')
    handoff=json.loads(payload);entry=handoff['eligible_models'][spec.model_key]
    if entry['sha256']!=spec.model_sha256:raise ValueError('frozen_worker_model_eligibility')
    frozen=Path(handoff['frozen_source_directory']);model_path=frozen/entry['path']
    from workflows.projected_release_v38 import verify_bundle
    from workflows.identify_sparse_world_v30 import from_record
    from koopman.bounded_mpc_v44 import load_fit_domains
    verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
    model_payload=model_path.read_bytes()
    if hashlib.sha256(model_payload).hexdigest()!=spec.model_sha256:raise ValueError('frozen_worker_model_hash')
    domain=load_fit_domains(root,model_path)[spec.configuration]
    if domain.identity!=spec.support_id or _context_key(spec.context)!=domain.context_key:
        raise ValueError('frozen_worker_fit_binding')
    if spec.compiler_directory is not None:
        compiler=Path(spec.compiler_directory).resolve()
        if not compiler.is_dir():raise ValueError('frozen_worker_compiler_missing')
        sys.path.insert(0,str(compiler))
    import numba,llvmlite
    if numba.__version__!='0.61.2' or llvmlite.__version__!='0.44.0':
        raise ValueError('frozen_worker_compiler_version')
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    from koopman.compiled_projected_v43 import prepare_compiled
    predictor=prepare_compiled(from_record(json.loads(model_payload)),spec.context)
    return RecoverySolver(domain,spec.context,predictor,config=spec.config,feedback_config=spec.feedback_config)
