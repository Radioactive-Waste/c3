from c3po.control.envelopes import *
from c3po.cobj.component import ControlComponent as CtrlComp
from c3po.cobj.group import ComponentGroup as CompGroup
from c3po.control.control import Control as Control
from c3po.control.control import ControlSet as ControlSet

from c3po.control.generator import Device as Device
from c3po.control.generator import AWG as AWG
from c3po.control.generator import Mixer as Mixer
from c3po.control.generator import Generator as Generator

import uuid

import tensorflow as tf

import matplotlib.pyplot as plt

from test_model import *
from test_generator import *

from c3po.optimizer.optimizer import Optimizer as Opt
from c3po.simulation.simulator import Simulator as Sim
from c3po.utils.tf_utils import *

import copy

env_group = CompGroup()
env_group.name = "env_group"
env_group.desc = "group containing all components of type envelop"


carr_group = CompGroup()
carr_group.name = "carr_group"
carr_group.desc = "group containing all components of type carrier"


carrier_parameters = {
    'freq' : 5.95e9 * 2 * np.pi
}

carr = CtrlComp(
    name = "carrier",
    desc = "Frequency of the local oscillator",
    params = carrier_parameters,
    groups = [carr_group.get_uuid()]
)
carr_group.add_element(carr)


flattop_params1 = {
    'amp' : np.pi * 1.2 / 7e-9, # 448964342.3828554,
    'T_up' : 3e-9,
    'T_down' : 10e-9,
    'xy_angle' : 0.0,
    'freq_offset' : 0e6 * 2 * np.pi, #150782.0898206234,
}


params_bounds = {
    'amp' : [50e6 * 2 * np.pi, 100e6 * 2 * np.pi],
    'T_up' : [1e-9, 11e-9],
    'T_down' : [1e-9, 11e-9],
    'xy_angle' : [-np.pi, np.pi],
    'freq_offset' : [-0.2e9 * 2 * np.pi, 0.2e9 * 2 * np.pi]
}

def my_flattop(t, params):
    t_up = tf.cast(params['T_up'], tf.float64)
    t_down = tf.cast(params['T_down'], tf.float64)
    T2 = tf.maximum(t_up, t_down)
    T1 = tf.minimum(t_up, t_down)
    return (1 + tf.math.erf((t - T1) / 1e-9)) / 2 * \
            (1 + tf.math.erf((-t + T2) / 1e-9)) / 2


p1 = CtrlComp(
    name = "pulse1",
    desc = "flattop comp 1 of signal 1",
    shape = my_flattop,
    params = flattop_params1,
    bounds = params_bounds,
    groups = [env_group.get_uuid()]
)
env_group.add_element(p1)


####
# Below code: For checking the single signal components
####

# t = np.linspace(0, 150e-9, int(150e-9*1e9))
# plt.plot(t, p1.get_shape_values(t))
# plt.plot(t, p2.get_shape_values(t))
# plt.show()


comps = []
comps.append(carr)
comps.append(p1)



ctrl = Control()
ctrl.name = "control1"
ctrl.t_start = 0.0
ctrl.t_end = 12e-9
ctrl.comps = comps


ctrls = ControlSet([ctrl])


awg = AWG()
mixer = Mixer()


devices = {
    "awg" : awg,
    "mixer" : mixer
}

resolutions = {
    "awg" : 1e9,
    "sim" : 5e11
}


resources = [ctrl]


resource_groups = {
    "env" : env_group,
    "carr" : carr_group
}


gen = Generator()
gen.devices = devices
gen.resolutions = resolutions
gen.resources = resources
gen.resource_groups = resource_groups

output = gen.generate_signals()

# from c3po.utils.tf_utils import *
# sess = tf_setup()
# for key in output.keys():
#     ts = sess.run(output[key]['ts'])
#     signal = sess.run(output[key]['signal'])
#     plt.plot(ts,signal)
#
# plt.show(block=False)

# gen.plot_signals()
# gen.plot_fft_signals()

# gen.plot_signals(resources)#sess = tf_debug.LocalCLIDebugWrapperSession(sess) # Enable this to debug
# gen.plot_fft_signals(resources)


# print(output)


# ts = output[(ctrl.name, ctrl.get_uuid())]["ts"]
# values = output[(ctrl.name, ctrl.get_uuid())]["signal"]


# plt.plot(ts, values)
# plt.show()



rechenknecht = Opt()
rechenknecht.store_history = True

tf_log_level_info()
set_tf_log_level(3)

print("current log level: " + str(get_tf_log_level()))

# to make sure session is empty look up: tf.reset_default_graph()

sess = tf_setup()

print(" ")
print("Available tensorflow devices: ")
tf_list_avail_devices()
writer = tf.summary.FileWriter( './logs/optim_log', sess.graph)
rechenknecht.set_session(sess)
rechenknecht.set_log_writer(writer)

opt_map = {
    'amp' : [(ctrl.get_uuid(), p1.get_uuid())],
    # 'T_up' : [
    #     (ctrl.get_uuid(), p1.get_uuid())
    #     ],
    # 'T_down' : [
    #     (ctrl.get_uuid(), p1.get_uuid())
    #     ],
    # 'xy_angle' : [(ctrl.get_uuid(), p1.get_uuid())],
    'freq_offset' : [(ctrl.get_uuid(), p1.get_uuid())]
}

sim = Sim(initial_model, gen, ctrls)

# Goal to drive on qubit 1
# U_goal = np.array(
#     [[0.+0.j, 1.+0.j, 0.+0.j],
#      [1.+0.j, 0.+0.j, 0.+0.j],
#      [0.+0.j, 0.+0.j, 1.+0.j]]
#     )

psi_init = np.array(
    [[1.+0.j],
     [0.+0.j]],
    )

psi_goal = np.array(
    [[0.+0.j],
     [1.+0.j]],
    )

sim.model = optimize_model

def evaluate_signals_psi(pulse_params, opt_params):
    model_params = sim.model.params
    U = sim.propagation(pulse_params, opt_params, model_params)
    psi_actual = tf.matmul(U, psi_init)
    overlap = tf.matmul(psi_goal.T, psi_actual)
    return 1-tf.cast(tf.conj(overlap)*overlap, tf.float64)

print(
"""
#######################
# Optimizing pulse... #
#######################
"""
)

def callback(xk):
    print(xk)

settings = {} #'maxiter': 5}

rechenknecht.optimize_controls(
    controls = ctrls,
    opt_map = opt_map,
    opt = 'lbfgs',
#    opt = 'tf_grad_desc',
    settings = settings,
    calib_name = 'openloop',
    eval_func = evaluate_signals_psi,
    callback = callback
    )
