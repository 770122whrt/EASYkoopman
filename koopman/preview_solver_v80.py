"""v79 causal preview with an explicit numerical interior for PWM planning.

The observed gate stays 2e-6. Exact CPU plans require 3e-6; the float64 NLP
targets 4e-6. These are engineering buffers, not a global CPU/GPU error proof.
Deployment still checks the actual backend allocation and actual receipts.
"""
import os
import time
import numpy as np
from koopman.feedback_preview_v79 import ExactChecker as PreviousChecker
from koopman.preview_mpc_v79 import PreviewMPC
from koopman.reliable_mpc_v77 import ProcessTransport as PreviousTransport, SynchronousLimits
from koopman.solver_worker_v49 import IsolatedSolverWorker
from koopman.model_separation_v79 import make_predictor
from koopman.control_objective_v44 import ObjectiveWeights
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig

PLANNING_MARGIN=3e-6
OPTIMIZER_MARGIN=4e-6


def enforce_interior(result,allocator,commands):
    if result['feasible']:
        raw=np.asarray([allocator.command(u,pre_tam=True)['pwm_raw'] for u in commands],dtype=float)
        if np.min(np.abs(np.abs(raw)-float(np.float32(.02))))<=PLANNING_MARGIN:
            return dict(feasible=False,reason='planning_pwm_interior',cost=None,predictions=None)
    return result


class ExactChecker(PreviousChecker):
    def check(self,origin,state,commands,previous,reference):
        checked=super().check(origin,state,commands,previous,reference)
        return enforce_interior(checked,self.plant.allocator,commands)


def tighten_deadzone_bounds(lower,horizon,num_thrusters):
    """Version-bound v76 constraint layout; refuse drift instead of guessing.

Each physics step has 11 state features and four scalar hard constraints;
each macro step has four slew, N raw PWM and N deadzone constraints.
"""
    low=np.asarray(lower,dtype=float).copy();h=horizon;n=num_thrusters
    if low.shape!=(60*h+h*(4+2*n),):raise ValueError('constraint_layout')
    for k in range(h):
        part=slice(60*h+k*(4+2*n)+4+n,60*h+(k+1)*(4+2*n))
        if not np.all(low[part]==2e-6):raise ValueError('constraint_layout')
        low[part]=OPTIMIZER_MARGIN
    return low


class _Engine:
    def __init__(self,spec):
        import torch
        torch.set_num_threads(1)
        from koopman.continuous_mpc_v80 import ContinuousMPC
        predictor=make_predictor(spec['kind'],spec['fitted'],spec['context'])
        self.solver=ContinuousMPC(spec['domain'],predictor,horizon=spec['horizon'],
                                  weights=spec['weights'],solve_seconds=30.)

    def __call__(self,request):
        cpu=time.process_time();request=dict(request)
        request['baseline']=request.pop('initial_guess')
        result=self.solver.solve(**request)
        result.update(worker_pid=os.getpid(),worker_cpu_seconds=time.process_time()-cpu,
            worker_threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        return result


class ProcessTransport(PreviousTransport):
    def __init__(self,spec,*,limits=SynchronousLimits(),engine_factory=_Engine):
        self.worker=IsolatedSolverWorker(engine_factory,spec,limits=limits)
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


def create_solver(domain,fitted,context,kind,*,horizon=20,weights=ObjectiveWeights(depth=4.),preview_enabled=True):
    predictor=make_predictor(kind,fitted,context)
    checker=ExactChecker(domain,predictor,horizon=horizon,weights=weights)
    spec=dict(domain=domain,fitted=fitted,context=context,kind=kind,horizon=horizon,weights=weights)
    worker=ProcessTransport(spec)
    def factory():return InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
    solver=PreviewMPC(checker,worker,factory,preview_enabled=preview_enabled)
    solver.model_identity=dict(kind=kind,symbolic_proxy='nominal_physics' if kind=='nominal_physics' else 'projected_koopman',
        unique_koopman_representation_claimed=False,pwm_planning_margin=PLANNING_MARGIN,pwm_optimizer_margin=OPTIMIZER_MARGIN)
    return solver
