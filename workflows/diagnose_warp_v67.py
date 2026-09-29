"""Bounded, read-only environment probe; not control or physics evidence."""
import argparse
import faulthandler
import json
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--embedded', action='store_true')
p.add_argument('--application', action='store_true')
a = p.parse_args()
faulthandler.enable(all_threads=True)
faulthandler.dump_traceback_later(30, repeat=True)
started = time.perf_counter()
if a.embedded:
    sys.path.insert(0, '/opt/conda/envs/isaaclab/lib/python3.11/site-packages/isaacsim/extscache/omni.warp.core-1.7.1+lx64')
import warp
print(json.dumps(dict(stage='import', version=warp.__version__, path=warp.__file__)), flush=True)
warp.init()
print(json.dumps(dict(stage='warp_initialized', devices=[str(d) for d in warp.get_devices()], seconds=time.perf_counter()-started)), flush=True)
if a.application:
    from isaacsim import SimulationApp
    app = SimulationApp(dict(headless=True, fast_shutdown=False))
    print(json.dumps(dict(stage='application_started', version=warp.__version__, path=warp.__file__, seconds=time.perf_counter()-started)), flush=True)
    app.close()
    print(json.dumps(dict(stage='application_closed', seconds=time.perf_counter()-started)), flush=True)
