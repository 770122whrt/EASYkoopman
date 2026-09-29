"""Bounded solver process with no pipe I/O on the low-level polling path.

Factories and pickle payloads are trusted, source-bound application code, not
untrusted network messages. This is process isolation for blocking computation,
not a security sandbox or proof that a returned plan is admissible to execute.
Lifecycle start/close and factory warmup occur outside control deadlines.
"""
from dataclasses import dataclass
import math
import multiprocessing
import numbers
import pickle
import threading
import time
import uuid


@dataclass(frozen=True)
class WorkerLimits:
    startup_timeout_s: float = 60.
    request_timeout_ms: float = 100.
    max_request_bytes: int = 256*1024
    max_result_bytes: int = 512*1024

    def __post_init__(self):
        for value,upper in ((self.startup_timeout_s,300.),(self.request_timeout_ms,10000.)):
            if isinstance(value,bool) or not isinstance(value,numbers.Real) or not math.isfinite(value) or not 0<value<=upper:
                raise ValueError('worker_time_limit')
        for value in (self.max_request_bytes,self.max_result_bytes):
            if type(value) is not int or not 1024<=value<=4*1024**2:
                raise ValueError('worker_payload_limit')


class _Mailbox:
    """One owned item; control-thread calls only try the lock."""
    def __init__(self):
        self._lock=threading.Lock();self._value=None;self.event=threading.Event()

    def offer(self,value):
        if not self._lock.acquire(blocking=False):return False
        try:
            if self._value is not None:return False
            self._value=value;self.event.set();return True
        finally:self._lock.release()

    def take(self):
        if not self._lock.acquire(blocking=False):return None
        try:
            value=self._value;self._value=None;self.event.clear();return value
        finally:self._lock.release()


def _worker_entry(factory,spec,receive,send,generation,limits):
    key=request_id=None
    def emit(kind,**values):
        packet=pickle.dumps(dict(kind=kind,generation=generation,**values),protocol=5)
        if len(packet)>limits.max_result_bytes:raise ValueError('worker_result_too_large')
        send.send_bytes(packet)
    try:
        solver=factory(spec)
        if not callable(solver):raise ValueError('worker_factory_not_callable')
        emit('ready')
        while True:
            packet=pickle.loads(receive.recv_bytes(limits.max_request_bytes))
            if packet['generation']!=generation:raise ValueError('worker_request_generation')
            key,request_id=packet['key'],packet['request_id']
            answer=solver(packet['payload'])
            if not isinstance(answer,dict):raise ValueError('worker_result_not_mapping')
            emit('result',key=key,request_id=request_id,payload=answer)
    except (EOFError,BrokenPipeError):
        pass
    except BaseException as exc:
        try:emit('error',key=key,request_id=request_id,error=(type(exc).__name__+':'+str(exc))[:512])
        except (Exception,KeyboardInterrupt):pass
    finally:
        receive.close();send.close()


class IsolatedSolverWorker:
    """Single control-thread owner, one outstanding request, bounded mailboxes.

    Timeout permanently disables this instance; late data never becomes a plan.
    A caller may close it and prepare a new instance outside the control loop,
    while retaining the execution ledger and incrementing its worker generation.
    """
    def __init__(self,factory,spec,*,limits=WorkerLimits()):
        if not callable(factory) or not isinstance(limits,WorkerLimits):raise ValueError('worker_setup')
        self._factory=factory;self._spec=spec;self.limits=limits
        self.generation=uuid.uuid4().hex;self.state='new';self._owner=threading.get_ident()
        self._outgoing=_Mailbox();self._incoming=_Mailbox();self._stop=threading.Event()
        self._process=None;self._threads=[];self._pipes=[];self._pending=None;self._sequence=0
        self._closed_result=None

    def _check_owner(self):
        if threading.get_ident()!=self._owner:raise RuntimeError('worker_control_owner_mismatch')

    def _publish(self,packet):
        while not self._stop.is_set():
            if self._incoming.offer(packet):return
            self._stop.wait(.001)

    def _write_loop(self,pipe):
        try:
            while not self._stop.is_set():
                self._outgoing.event.wait(.05)
                packet=self._outgoing.take()
                if packet is not None and not self._stop.is_set():pipe.send_bytes(packet)
        except (OSError,EOFError) as exc:
            self._publish(dict(kind='transport_error',generation=self.generation,error=str(exc)[:512]))

    def _read_loop(self,pipe):
        try:
            while not self._stop.is_set():
                data=pipe.recv_bytes(self.limits.max_result_bytes)
                packet=pickle.loads(data)
                if not isinstance(packet,dict):raise ValueError('worker_envelope_not_mapping')
                self._publish(packet)
        except Exception as exc:
            self._publish(dict(kind='transport_error',generation=self.generation,error=(type(exc).__name__+':'+str(exc))[:512]))

    def start(self):
        self._check_owner()
        if self.state!='new':raise ValueError('worker_already_started')
        ctx=multiprocessing.get_context('spawn')
        child_receive,parent_send=ctx.Pipe(duplex=False)
        parent_receive,child_send=ctx.Pipe(duplex=False)
        self._pipes=[parent_send,parent_receive]
        self._process=ctx.Process(target=_worker_entry,
            args=(self._factory,self._spec,child_receive,child_send,self.generation,self.limits),daemon=True)
        self.state='starting';self._started=time.perf_counter()
        try:self._process.start()
        except Exception:
            self.state='failed'
            for pipe in (child_receive,parent_send,parent_receive,child_send):pipe.close()
            raise
        child_receive.close();child_send.close()
        self._threads=[threading.Thread(target=self._write_loop,args=(parent_send,),daemon=True),
                       threading.Thread(target=self._read_loop,args=(parent_receive,),daemon=True)]
        for thread in self._threads:thread.start()

    def submit(self,request_id,payload):
        self._check_owner()
        if self.state!='ready':return dict(status='rejected',reason='worker_not_ready')
        if not isinstance(request_id,str) or not request_id.strip() or len(request_id)>256:
            return dict(status='rejected',reason='request_identity_invalid')
        started=time.perf_counter();deadline=started+self.limits.request_timeout_ms/1000
        key=f'{self.generation}:{self._sequence}'
        try:
            packet=pickle.dumps(dict(generation=self.generation,key=key,request_id=request_id,payload=payload),protocol=5)
        except Exception as exc:return dict(status='rejected',reason='request_serialization:'+type(exc).__name__)
        if len(packet)>self.limits.max_request_bytes:return dict(status='rejected',reason='request_too_large')
        if time.perf_counter()>=deadline:return dict(status='rejected',reason='request_serialization_timeout')
        if not self._outgoing.offer(packet):return dict(status='rejected',reason='request_mailbox_busy')
        self._pending=dict(key=key,request_id=request_id,deadline=deadline,started=started)
        self._sequence+=1;self.state='busy'
        return dict(status='accepted',key=key,generation=self.generation,request_id=request_id)

    def _failure(self,reason,*,timeout=False):
        event=dict(status='timeout' if timeout else 'failed',reason=reason,generation=self.generation,
            request_id=None if self._pending is None else self._pending['request_id'],
            key=None if self._pending is None else self._pending['key'])
        self.state='timed_out' if timeout else 'failed';self._pending=None
        return event

    def poll(self):
        self._check_owner()
        if self.state in ('new','closed','failed','timed_out'):return None
        now=time.perf_counter()
        if self.state=='starting' and now-self._started>=self.limits.startup_timeout_s:
            return self._failure('worker_prepare_timeout',timeout=True)
        if self._pending is not None and now>=self._pending['deadline']:
            return self._failure('worker_request_timeout',timeout=True)
        packet=self._incoming.take()
        if packet is not None:
            if packet.get('generation')!=self.generation:return self._failure('worker_generation_mismatch')
            kind=packet.get('kind')
            if kind in ('error','transport_error'):return self._failure(packet.get('error','worker_error'))
            if self._process.exitcode is not None:return self._failure('worker_exited:'+str(self._process.exitcode))
            if kind=='ready' and self.state=='starting':
                self.state='ready';return dict(status='ready',generation=self.generation)
            if kind!='result' or self._pending is None:return self._failure('worker_unexpected_reply')
            pending=self._pending
            if packet.get('key')!=pending['key'] or packet.get('request_id')!=pending['request_id']:
                return self._failure('worker_request_binding_mismatch')
            # Receipt/decoding is included; even an already-computed late reply is rejected.
            if time.perf_counter()>=pending['deadline']:return self._failure('worker_request_timeout',timeout=True)
            if not isinstance(packet.get('payload'),dict):return self._failure('worker_result_not_mapping')
            self._pending=None;self.state='ready'
            return dict(status='result',generation=self.generation,key=pending['key'],
                request_id=pending['request_id'],payload=packet['payload'],
                elapsed_ms=1000*(time.perf_counter()-pending['started']),runtime_eligible=False)
        if self._process.exitcode is not None:return self._failure('worker_exited:'+str(self._process.exitcode))
        return None

    def close(self,*,join_seconds=2.):
        """Explicit lifecycle cleanup; never called by submit/poll on a timeout."""
        self._check_owner()
        if not isinstance(join_seconds,numbers.Real) or not math.isfinite(join_seconds) or not 0<join_seconds<=10:
            raise ValueError('worker_close_budget')
        if self._closed_result is not None:return dict(self._closed_result)
        self.state='closed';self._stop.set();end=time.perf_counter()+join_seconds
        process=self._process
        if process is not None and process.pid is not None:
            if process.is_alive():process.terminate()
            process.join(max(0.,end-time.perf_counter()))
        for thread in self._threads:thread.join(max(0.,end-time.perf_counter()))
        for pipe in self._pipes:pipe.close()
        stopped=process is None or process.pid is None or not process.is_alive()
        result=dict(process_stopped=stopped,io_threads_stopped=not any(t.is_alive() for t in self._threads))
        if stopped and process is not None:process.close()
        self._closed_result=result;return dict(result)
