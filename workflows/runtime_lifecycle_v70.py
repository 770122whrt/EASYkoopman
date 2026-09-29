"""Release owned physics observers before SimulationApp unloads native plugins.

The caller transfers ownership in a mutable dict and MUST clear its aliases
before calling. This is a lifetime repair, never a substitute for native exit 0.
"""
import gc
import json
import weakref
from pathlib import Path


def release_native_aliases(environment):
    """Release EasyUUV's extra robot owner after DirectRLEnv.close deletes scene.

    A cached exception can retain an otherwise closed environment until Python
    finalization. It must not carry a PhysX SimulationView past app shutdown.
    Neither the environment nor any trace is advanced here.
    """
    core=getattr(environment,'unwrapped',environment)
    if '_robot' not in vars(core):
        return dict(robot_alias_present=False,robot_released=True)
    if getattr(core,'_is_closed',False) is not True:
        raise ValueError('native_alias_environment_not_closed')
    robot_ref=weakref.ref(core._robot)
    del core._robot
    gc.collect()
    result=dict(robot_alias_present=True,robot_released=robot_ref() is None)
    if not result['robot_released']:
        raise ValueError('native_robot_still_retained_after_close')
    return result


def release_observer(trace):
    if trace is None:return
    if trace.active:raise ValueError('cannot_release_active_observer')
    trace.contact_getter=None
    trace.originals.clear()
    trace.instance_values.clear()
    trace.actuator_original=None
    trace.actuator_instance_value=None
    trace.env=None
    trace.runtime=None


def close_owned_resources(resources,report,output):
    report['cleanup_completed']=dict(worker=False,environment=False,simulation_app=False)
    def record(index,name,phase):
        with (Path(output)/f'cleanup-{index:02d}-{name}-{phase}.json').open('x',encoding='utf8') as f:
            json.dump(dict(resource=name,phase=phase,status=report['status'],exception=report.get('exception'),
                cleanup_completed=dict(report['cleanup_completed']),cleanup_errors=list(report['cleanup_errors']),
                worker_closed=report.get('worker_closed')),f,indent=2)
    for index,(key,name) in enumerate((('worker','worker'),('env','environment'),('app','simulation_app')),1):
        record(index,name,'begin')
        resource=resources.pop(key,None)
        trace=None
        try:
            if key=='env':
                trace=resources.pop('trace',None)
                release_observer(trace)
                trace=None
                resources.pop('runtime',None)
            if resource is not None:
                result=resource.close()
                if key=='env':
                    report['native_alias_release']=release_native_aliases(resource)
                if key=='worker':
                    report['worker_closed']=result
                    if result!={'process_stopped':True,'io_threads_stopped':True}:
                        raise RuntimeError('worker_not_fully_closed')
                report['cleanup_completed'][name]=True
        except BaseException as exc:
            report['cleanup_errors'].append(name+':'+type(exc).__name__+':'+str(exc))
        finally:
            trace=None
            resource=None
            if key=='env':
                report['native_dependents_gc_collected']=gc.collect()
        record(index,name,'end')
