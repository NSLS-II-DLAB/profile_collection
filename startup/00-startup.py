
from bluesky import RunEngine, Msg
from ophyd import EpicsMotor, EpicsSignal, EpicsSignalWithRBV, EpicsSignalRO, DeviceStatus
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager
import bluesky.preprocessors as bp

import bluesky.plan_stubs as bps

from megatron.support import register_custom_instructions
from megatron.interpreter import Interpreter

import re
import time
import numpy as np
import asyncio
import uuid

galil = EpicsMotor('sim:mtr1', name='galil')
galil_signal = EpicsSignalRO('sim:mtr1.RBV', name='galil_signal', auto_monitor=True)

RE = RunEngine({})

#bec = BestEffortCallback()
#RE.subscribe(bec)
RE.waiting_hook = ProgressBarManager()

register_custom_instructions(re=RE)

devices = {"galil": galil, "galil_signal": galil_signal}
# devices = {"galil": galil, "galil_signal": galil}

support = Interpreter(devices=devices)

@bp.reset_positions_decorator([galil.velocity])
def execute_script(script_path):
    script = []
    with open(script_path, "rt") as f:
        script = [_.strip(" \n") for _ in f.readlines()]
    print(f"{script = }")
    for s in script:
        yield from support._process_line(s)
