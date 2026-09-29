"""Command-only replay using the runtime's float32 PWM deadzone predicate.

The original v24 estimator is preserved for frozen experiments. Its float64
comparison classified float32(0.02) as below threshold; the actual plant's
float32 tensor compares it equal. No measured rotor correction is used here.
"""
import math
import numpy as np
from easyuuv_nc.control import ActuatorState


class Float32PWMActuatorState(ActuatorState):
    def advance_pwm(self, pwm):
        command = np.asarray(pwm, dtype=float)
        if (command.shape != self._speed.shape or not np.isfinite(command).all()
                or np.any(np.abs(command) > 1)):
            raise ValueError('direct_actuator_pwm_invalid')
        command = command.astype(np.float32).astype(float)
        threshold = float(np.float32(.02))
        positive, negative = command >= threshold, command <= -threshold
        target = np.zeros_like(command)
        target[positive] = -139*command[positive]**2 + 500*command[positive] + 8.28
        target[negative] = 161*command[negative]**2 + 517.86*command[negative] - 5.72
        if self.clock == 'float32_accumulated_v1':
            next_time = float(np.float32(np.float32(self.elapsed_time) + np.float32(self.dt)))
            alpha = math.exp(-(next_time-self.elapsed_time)/self.tau)
            self.elapsed_time = next_time
        else:
            alpha = self.alpha
            self.elapsed_time += self.dt
        self._speed = alpha*self._speed + (1-alpha)*target
        return self.current()
