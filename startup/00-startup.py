from datetime import datetime

from bluesky import RunEngine, Msg
from ophyd import EpicsMotor, EpicsSignal, EpicsSignalWithRBV, EpicsSignalRO, DeviceStatus, Component as Cpt
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager
import bluesky.preprocessors as bp
import bluesky.plan_stubs as bps

from megatron.support import register_custom_instructions
from megatron.interpreter import Interpreter, ts_periodic_logging_decorator

class EpicsMotorGalil(EpicsMotor):
    homing_monitor = Cpt(EpicsSignalRO, ".A_HOMING_MONITOR", kind="omitted", auto_monitor=True)
    channel_enable = Cpt(EpicsSignal, ".CNEN", kind="omitted", auto_monitor=True)

galil = EpicsMotorGalil('sim:mtr1', name='galil')
galil_val = EpicsSignal('sim:mtr1.VAL', name='galil_val', auto_monitor=True)
galil_rbv = EpicsSignalRO('sim:mtr1.RBV', name='galil_rbv', auto_monitor=True)

RE = RunEngine({})

#bec = BestEffortCallback()
#RE.subscribe(bec)
RE.waiting_hook = ProgressBarManager()

register_custom_instructions(re=RE)

devices = {"galil": galil, "galil_val": galil_val, "galil_rbv": galil_rbv}

interpreter = Interpreter(devices=devices)

logging_dir = "./logs"

@bp.reset_positions_decorator([galil.velocity])
def execute_script(script_path):
    script = []
    with open(script_path, "rt") as f:
        script = [_.strip(" \n") for _ in f.readlines()]
    print(f"{script = }")

    for s in script:
        yield from interpreter._process_line(s, scan_for_logs=True)

    for k,v in interpreter.logged_signals.items():
        print(f"{k}: {v}")

    # Generate log file name based on current date and time
    log_file_name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    log_file_path = f"{logging_dir}/{log_file_name}"

    print(f"Logs are saved to {log_file_path!r}")

    @ts_periodic_logging_decorator(
        signals=interpreter.logged_signals,
        log_file_path=log_file_path,
        period=1,
    )
    def _inner():
        for s in script:
            yield from interpreter._process_line(s)

    yield from _inner()
