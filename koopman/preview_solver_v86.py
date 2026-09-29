"""Three frozen model arms using the same continuous solver and admission path."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import time
from koopman.disturbance_lifted_v86 import prepare,physical_identity
from koopman.preview_solver_v80 import ExactChecker,ProcessTransport,PLANNING_MARGIN,OPTIMIZER_MARGIN
from koopman.preview_mpc_v79 import PreviewMPC
from koopman.control_objective_v44 import ObjectiveWeights
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig
from workflows.protocol_v86 import case_spec
from workflows.fit_disturbance_v86 import load_record

KINDS=('physics','koopman','hybrid')


@dataclass(frozen=True)
class LoadedModel:
    path: str
    file_sha256: str
    record: dict


def load_model(path,expected_sha256):
    path=Path(path).resolve();sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha!=expected_sha256:raise ValueError('v86_artifact_hash')
    record,_=load_record(path)
    return LoadedModel(str(path),sha,record)


def make_predictor(kind,loaded,context):
    from workflows.identify_sparse_world_v30 import from_record
    from koopman.physical_control_v76 import PhysicalPredictor
    if kind not in KINDS:raise ValueError('v86_model_kind')
    physical=PhysicalPredictor(from_record(loaded.record['physical_prior']),context,identified=True)
    if physical_identity(physical)!=loaded.record['physical_identity']:raise ValueError('v86_context_binding')
    return physical if kind=='physics' else prepare(loaded.record,context,physical,kind=kind)


def verify_support(loaded,assets):
    sources={name:digest for d in assets.domains.values() for name,digest in d.fit_sources}
    if sources!=loaded.record['physical_prior']['fit_episode_hashes']:raise ValueError('v86_common_support_sources')


def model_identity(loaded,kind):
    if kind not in KINDS:raise ValueError('v86_model_kind')
    return dict(kind=kind,prediction_content_sha256=loaded.record['content_sha256'],
        physical_content_sha256=loaded.record['physical_identity'],full_latent_propagation=kind!='physics',
        physical_recalibrated=False,online_learning=False,real_time_qualified=False)


def _verify_domain(loaded,domain):
    sources=loaded.record['physical_prior']['fit_episode_hashes']
    if domain.configuration!='base' or any(sources.get(n)!=s for n,s in domain.fit_sources):
        raise ValueError('v86_domain')


class _Engine:
    def __init__(self,spec):
        import torch
        torch.set_num_threads(1)
        from koopman.continuous_mpc_v80 import ContinuousMPC
        loaded=load_model(spec['model'],spec['sha256']);_verify_domain(loaded,spec['domain'])
        predictor=make_predictor(spec['kind'],loaded,spec['context'])
        self.solver=ContinuousMPC(spec['domain'],predictor,horizon=spec['horizon'],weights=spec['weights'],solve_seconds=30.)

    def __call__(self,request):
        cpu=time.process_time();request=dict(request);request['baseline']=request.pop('initial_guess')
        result=self.solver.solve(**request)
        result.update(worker_pid=os.getpid(),worker_cpu_seconds=time.process_time()-cpu)
        return result


def create_solver(domain,context,kind,*,learned_model,learned_sha256,horizon=20,
                  weights=ObjectiveWeights(depth=4.),preview_enabled=True):
    loaded=load_model(learned_model,learned_sha256);_verify_domain(loaded,domain)
    predictor=make_predictor(kind,loaded,context)
    checker=ExactChecker(domain,predictor,horizon=horizon,weights=weights)
    worker=ProcessTransport(dict(domain=domain,context=context,kind=kind,model=loaded.path,
        sha256=loaded.file_sha256,horizon=horizon,weights=weights),engine_factory=_Engine)
    def factory():return InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
    solver=PreviewMPC(checker,worker,factory,preview_enabled=preview_enabled)
    solver.model_identity=model_identity(loaded,kind)
    return solver
