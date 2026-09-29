"""Bounded wall/CPU/GC attribution, with optional episode-only GC deferral."""
import gc,time,resource

def measured_episode(session,report,run,*,defer_gc=False):
    fb=session.runtime.feedback;original=fb.decide;enabled=gc.isenabled()
    timing=dict(defer_gc=defer_gc,feedback=[],gc_events=[],rss_before_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report['latency_probe_v67']=timing
    def callback(phase,info):
        if len(timing['gc_events'])<512:timing['gc_events'].append(dict(phase=phase,generation=info['generation'],wall=time.perf_counter(),cpu=time.process_time(),thread=time.thread_time()))
    def decide(*args,**kwargs):
        start=time.perf_counter();cpu=time.process_time();thread=time.thread_time()
        try:return original(*args,**kwargs)
        finally:timing['feedback'].append(dict(start=start,end=time.perf_counter(),wall_ms=1000*(time.perf_counter()-start),cpu_ms=1000*(time.process_time()-cpu),thread_ms=1000*(time.thread_time()-thread),physics_index=session.runtime.ledger.physics_index))
    fb.decide=decide;gc.callbacks.append(callback)
    try:
        if defer_gc:
            before=time.perf_counter();gc.collect();timing['prepare_collect_ms']=1000*(time.perf_counter()-before);gc.disable()
        return run()
    finally:
        fb.decide=original;gc.callbacks.remove(callback)
        if enabled:gc.enable()
        timing['rss_after_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;timing['gc_restored']=gc.isenabled()==enabled
        if timing['rss_after_kib']-timing['rss_before_kib']>64*1024:raise ValueError('bounded_gc_memory_growth')
