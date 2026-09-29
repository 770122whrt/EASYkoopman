"""Known instantaneous input kick plus a learned full lifted-state increment.

The finite-step kick is an explicit approximation; this hybrid is not a
constant A/B linear plant. Historical free-input v24 fits remain unchanged.
"""
from dataclasses import dataclass
import numpy as np
from koopman.projected_edmd_v24 import observable, decode, _readonly


def input_kick(states, acceleration):
    x=np.asarray(states,dtype=float);a=np.asarray(acceleration,dtype=float)
    if (x.ndim!=2 or x.shape[1]!=11 or a.shape!=(len(x),6)
            or not np.isfinite(x).all() or not np.isfinite(a).all()):
        raise ValueError('known_input_invalid')
    y=x.copy();y[:,5:11]+=a/120
    return y


def remove_known_input(current, following, acceleration, context, dictionary):
    phi=observable(current,context,dictionary)
    effect=observable(input_kick(current,acceleration),context,dictionary)-phi
    return phi,observable(following,context,dictionary)-effect


@dataclass(frozen=True)
class StateOperator:
    mean: np.ndarray
    scale: np.ndarray
    bias: np.ndarray
    coefficient: np.ndarray
    audit: dict

    def bind(self, context, dictionary):
        if dictionary not in ('linear','nonlinear') or len(self.mean)!={'linear':25,'nonlinear':58}[dictionary]:
            raise ValueError('structured_dictionary_invalid')
        return BoundOperator(self,context,dictionary)


@dataclass(frozen=True)
class BoundOperator:
    state_operator: StateOperator
    context: object
    dictionary: str

    @property
    def mean(self):return self.state_operator.mean

    @property
    def scale(self):return self.state_operator.scale

    def advance_lift(self, z, inputs):
        op=self.state_operator
        inputs=np.asarray(inputs,dtype=float)
        if inputs.shape!=(len(z),6) or not np.isfinite(inputs).all():
            raise ValueError('known_input_invalid')
        states=decode(z*op.scale+op.mean)
        valid=np.isfinite(states).all(axis=1)
        result=np.full_like(z,np.nan,dtype=float)
        effect=(observable(input_kick(states[valid],inputs[valid]),self.context,self.dictionary)
                -observable(states[valid],self.context,self.dictionary))
        result[valid]=z[valid]+op.bias+z[valid]@op.coefficient+effect/op.scale
        return result


def fit_state_operator(current, following_minus_known_effect):
    a=np.asarray(current,dtype=float);b=np.asarray(following_minus_known_effect,dtype=float)
    if (a.ndim!=2 or a.shape!=b.shape or len(a)<2 or not a.shape[1]
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        raise ValueError('operator_fit_invalid')
    mean=a.mean(0);scale=np.maximum(a.std(0),1e-6);design=(a-mean)/scale
    target=(b-a)/scale;bias=target.mean(0)
    left,singular,right=np.linalg.svd(design,full_matrices=False)
    smallest=singular[-1]**2/len(a) if len(singular)==design.shape[1] else 0.
    condition=(singular[0]**2/len(a)+.001)/(smallest+.001)
    if not np.isfinite(condition) or condition>1e8:raise ValueError('operator_condition_invalid')
    coefficient=(right.T*(singular/(singular**2+len(a)*.001)))@(left.T@(target-bias))
    residual=target-bias-design@coefficient
    audit={'fit_rows':len(a),'target_observables':a.shape[1],'inputs':0,
           'learned_force_coefficients':0,'input_map':'known_explicit_dtI_kick','full_lift_operator':True,
           'rank':int(np.sum(singular>singular[0]*max(design.shape)*np.finfo(float).eps)),
           'singular_values':singular.tolist(),'regularized_condition':float(condition),'mean_ridge':.001,
           'standardized_increment_fit_rmse':np.sqrt(np.mean(residual**2,axis=0)).tolist()}
    return StateOperator(*map(_readonly,(mean,scale,bias,coefficient)),audit)
