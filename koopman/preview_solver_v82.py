"""Explicit learned/same-data-physics predictors inside the same v80 MPC.

The v81 record is authenticated independently of the old common-support asset.
Both parent admission and isolated optimization reconstruct their own predictor.
This development interface does not promote a model into the v38 contract.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
import numpy as np
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.learned_velocity_v81 import prepare_learned, validate_record
from koopman.physical_control_v76 import PhysicalPredictor
from koopman.preview_solver_v80 import ExactChecker, PLANNING_MARGIN, OPTIMIZER_MARGIN
from koopman.preview_mpc_v79 import PreviewMPC
from koopman.reliable_mpc_v77 import ProcessTransport as PreviousTransport, SynchronousLimits
from koopman.solver_worker_v49 import IsolatedSolverWorker
from koopman.control_objective_v44 import ObjectiveWeights
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig
from workflows.protocol_v80 import case_spec as common_case_spec

KINDS=('learned_velocity','matched_physics')


@dataclass(frozen=True)
class LoadedModel:
    path: str
    file_sha256: str
    record: dict


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def load_model(path,expected_sha256):
    if not isinstance(expected_sha256,str) or not re.fullmatch('[0-9a-f]{64}',expected_sha256):
        raise ValueError('learned_artifact_hash')
    path=Path(path).resolve();payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha256:raise ValueError('learned_artifact_hash')
    record=json.loads(payload);validate_record(record,expected_sha256=record.get('content_sha256'))
    configs=record['physical_prior']['configurations']
    if (len(configs)!=8 or set(configs)!=set(SUPPORTED_EMBODIMENTS)
            or record['audit']['fit_episodes']!=24
            or len(record['physical_prior']['fit_episode_hashes'])!=24):
        raise ValueError('pooled_fit_inventory')
    return LoadedModel(str(path),expected_sha256,record)


def make_predictor(kind,loaded,context):
    if kind not in KINDS:raise ValueError('learned_model_kind')
    prior,_=validate_record(loaded.record,expected_sha256=loaded.record['content_sha256'])
    if kind=='learned_velocity':
        return prepare_learned(loaded.record,context,expected_sha256=loaded.record['content_sha256'])
    return PhysicalPredictor(prior,context,identified=True)


def model_identity(loaded,kind):
    if kind not in KINDS:raise ValueError('learned_model_kind')
    record=loaded.record
    return dict(kind=kind,symbolic_proxy='learned_velocity_matrix_v81' if kind=='learned_velocity' else 'same_record_identified_physics_v81',
        prediction_artifact_sha256=loaded.file_sha256,
        prediction_record_content_sha256=record['content_sha256'],
        prediction_content_sha256=record['content_sha256'] if kind=='learned_velocity' else _canonical_sha(record['physical_prior']),
        uses_learned_velocity_matrix=kind=='learned_velocity',representation_benefit_claimed=False,
        v38_model_admission_claimed=False,comparison_scope='pooled_fit8_development',fit_episode_count=24,
        pwm_planning_margin=PLANNING_MARGIN,pwm_optimizer_margin=OPTIMIZER_MARGIN)


def verify_support(loaded,assets):
    """Bind all 24 training source identities to the authenticated common fit data."""
    sources={name:digest for domain in assets.domains.values() for name,digest in domain.fit_sources}
    if sources!=loaded.record['physical_prior']['fit_episode_hashes']:
        raise ValueError('learned_common_fit_sources')


def _verify_domain(loaded,domain):
    source=loaded.record['physical_prior']['fit_episode_hashes']
    if len(domain.fit_sources)!=3 or any(source.get(name)!=digest for name,digest in domain.fit_sources):
        raise ValueError('learned_domain_fit_sources')


def case_spec(configuration,controller,preview_enabled,task):
    if controller not in KINDS:raise ValueError('learned_model_kind')
    case=common_case_spec(configuration,'identified_physics',preview_enabled,task)
    case['controller']=controller
    return case


class _Engine:
    def __init__(self,spec):
        import torch
        torch.set_num_threads(1)
        from koopman.continuous_mpc_v80 import ContinuousMPC
        loaded=load_model(spec['learned_model'],spec['learned_sha256'])
        _verify_domain(loaded,spec['domain'])
        predictor=make_predictor(spec['kind'],loaded,spec['context'])
        self.solver=ContinuousMPC(spec['domain'],predictor,horizon=spec['horizon'],
                                  weights=spec['weights'],solve_seconds=30.)

    def __call__(self,request):
        cpu=time.process_time();request=dict(request);request['baseline']=request.pop('initial_guess')
        result=self.solver.solve(**request)
        result.update(worker_pid=os.getpid(),worker_cpu_seconds=time.process_time()-cpu,
            worker_threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        return result


class ProcessTransport(PreviousTransport):
    def __init__(self,spec,*,limits=SynchronousLimits()):
        self.worker=IsolatedSolverWorker(_Engine,spec,limits=limits)
        keys=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS');prior={k:os.environ.get(k) for k in keys}
        try:
            for k in keys:os.environ[k]='1'
            self.worker.start()
        finally:
            for k,v in prior.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
        self.sequence=0
        try:
            event=self._wait()
            if event['status']!='ready':raise RuntimeError('solver_startup:'+str(event))
        except BaseException:self.worker.close();raise
        self.pid=self.worker._process.pid
        if self.pid==os.getpid():raise RuntimeError('worker_not_isolated')


def create_solver(domain,context,kind,*,learned_model,learned_sha256,horizon=20,
                  weights=ObjectiveWeights(depth=4.),preview_enabled=True):
    loaded=load_model(learned_model,learned_sha256);_verify_domain(loaded,domain)
    predictor=make_predictor(kind,loaded,context)
    checker=ExactChecker(domain,predictor,horizon=horizon,weights=weights)
    spec=dict(domain=domain,context=context,kind=kind,learned_model=loaded.path,learned_sha256=loaded.file_sha256,
              horizon=horizon,weights=weights)
    worker=ProcessTransport(spec)
    def factory():return InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
    solver=PreviewMPC(checker,worker,factory,preview_enabled=preview_enabled)
    solver.model_identity=model_identity(loaded,kind)
    return solver
