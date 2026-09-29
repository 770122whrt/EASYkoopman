"""Validate the fixed simulator mechanics before command prediction."""
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.physics_context import PhysicalContext
from workflows.mechanics import mechanics
def validate_context(configuration,context):
    """Reject a different body/physics context in this static-catalog interface.

    These are admission checks, not estimates of actual runtime parameters.
    Live use still requires the runtime readback/initialization evidence gate.
    """
    m=mechanics(configuration)
    expected=PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],
        EMBODIMENT_CONFIGS[configuration]['drag_multiplier'],rho=m['water_density_kg_m3'],gravity=m['gravity_m_s2'])
    # PhysX stores inverse mass, then getMass reciprocates it again. Admit
    # only the authored float32 value or this specific float32 roundtrip.
    # Do not replace the caller's observed mass used in acceleration/prediction.
    roundtrip=float(np.float32(1)/np.float32(np.float32(1)/np.float32(expected.mass)))
    if (not isinstance(context,PhysicalContext) or context.mass not in (expected.mass,roundtrip)
        or any(not np.array_equal(getattr(context,k),getattr(expected,k))
            for k in ('inertia','cob','volume','drag_multiplier','rho','beta','gravity'))):
        raise ValueError('command_context_mismatch')
    return m
