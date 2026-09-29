"""Real spawned-worker isolation, distinct from solver and Isaac validation."""
import multiprocessing
import os
import time

import pytest


def make_solver(spec):
    if spec.get('prepare_error'):raise ValueError('fixture prepare failed')
    if spec.get('prepare_delay'):time.sleep(spec['prepare_delay'])
    def solve(payload):
        if spec.get('started') is not None:spec['started'].set()
        if payload.get('exit'):os._exit(7)
        if payload.get('block'):time.sleep(payload['block'])
        if payload.get('raise'):raise ValueError('fixture solve failed')
        if payload.get('unserializable'):return lambda:None
        if payload.get('large'):return {'body':'x'*payload['large']}
        return {'value':payload.get('value'),'pid':os.getpid()}
    return solve


def make_worker(**kwargs):
    from koopman.solver_worker_v49 import IsolatedSolverWorker,WorkerLimits
    spec=kwargs.pop('spec',{})
    worker=IsolatedSolverWorker(make_solver,spec,limits=WorkerLimits(startup_timeout_s=20,**kwargs))
    worker.start();return worker


def wait_event(worker,kind,limit=10):
    end=time.perf_counter()+limit
    while time.perf_counter()<end:
        event=worker.poll()
        if event is not None:
            assert event['status']==kind,event
            return event
        time.sleep(.005)
    raise AssertionError('worker event not received')


def test_spawned_solver_returns_owned_packet_without_access_to_live_controller():
    worker=make_worker(request_timeout_ms=3000)
    try:
        wait_event(worker,'ready')
        source={'value':[1,2]};accepted=worker.submit('request-1',source)
        assert accepted['status']=='accepted'
        source['value'][0]=99
        event=wait_event(worker,'result')
        assert event['payload']['value']==[1,2] and event['payload']['pid']!=os.getpid()
        assert event['request_id']=='request-1' and event['key']==accepted['key']
        assert worker.state=='ready'
    finally:assert worker.close()['process_stopped']


def test_blocked_solver_cannot_block_poll_or_admit_a_second_request():
    started=multiprocessing.get_context('spawn').Event()
    worker=make_worker(spec={'started':started},request_timeout_ms=3000)
    try:
        wait_event(worker,'ready');assert worker.submit('blocked',{'block':5})['status']=='accepted'
        assert started.wait(5)
        t=time.perf_counter()
        for _ in range(100):
            assert worker.poll() is None
            assert worker.submit('second',{})=={'status':'rejected','reason':'worker_not_ready'}
        elapsed=time.perf_counter()-t
        assert elapsed<.2,elapsed  # Isolation check, not a 16.67ms runtime certificate.
    finally:
        closed=worker.close();assert closed['process_stopped'] and closed['io_threads_stopped']


def test_deadline_disables_worker_and_late_reply_is_never_promoted():
    worker=make_worker(request_timeout_ms=40)
    try:
        wait_event(worker,'ready');worker.submit('late',{'block':.3})
        event=wait_event(worker,'timeout');assert event['request_id']=='late'
        time.sleep(.35)
        assert worker.poll() is None and worker.state=='timed_out'
        assert worker.submit('next',{})['status']=='rejected'
    finally:worker.close()


@pytest.mark.parametrize('payload',[{'raise':True},{'unserializable':True},{'large':10000},{'exit':True}])
def test_worker_errors_and_oversized_reply_fail_closed(payload):
    worker=make_worker(request_timeout_ms=3000,max_result_bytes=2048)
    try:
        wait_event(worker,'ready');worker.submit('bad',payload)
        assert wait_event(worker,'failed')['reason']
        assert worker.state=='failed' and worker.submit('new',{})['status']=='rejected'
    finally:worker.close()


def test_bad_or_oversized_request_does_not_enter_pending_slot():
    worker=make_worker(request_timeout_ms=3000,max_request_bytes=1024)
    try:
        wait_event(worker,'ready')
        for value in ({'bad':lambda:None},{'large':'x'*2048}):
            assert worker.submit('bad',value)['status']=='rejected'
            assert worker.state=='ready'
        assert worker.submit('good',{'value':7})['status']=='accepted'
        assert wait_event(worker,'result')['payload']['value']==7
    finally:worker.close()


def test_prepare_failure_never_emits_ready():
    worker=make_worker(spec={'prepare_error':True})
    try:
        assert wait_event(worker,'failed')['reason']
        assert worker.submit('new',{})['status']=='rejected'
    finally:worker.close()


def test_prepare_timeout_is_nonblocking_and_does_not_require_cooperative_factory():
    from koopman.solver_worker_v49 import IsolatedSolverWorker,WorkerLimits
    worker=IsolatedSolverWorker(make_solver,{'prepare_delay':5},limits=WorkerLimits(startup_timeout_s=.1))
    worker.start()
    try:
        event=wait_event(worker,'timeout');assert event['reason']=='worker_prepare_timeout'
        assert worker.state=='timed_out'
    finally:worker.close()


@pytest.mark.parametrize('field,value',[('request_timeout_ms',0),('startup_timeout_s',float('nan')),('max_request_bytes',False),('max_result_bytes',10**9)])
def test_invalid_limits_cannot_create_unbounded_worker(field,value):
    from koopman.solver_worker_v49 import WorkerLimits
    with pytest.raises(ValueError):WorkerLimits(**{field:value})
