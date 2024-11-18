from datetime import datetime

import bluesky.preprocessors as bp
from bluesky import RunEngine

# from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager
from megatron.interpreter import Interpreter, ts_periodic_logging_decorator
from megatron.support import EpicsMotorGalil, register_custom_instructions, ION_Pump_PS
from ophyd import EpicsSignal, EpicsSignalRO

#prefix = "Test{DMC:1}A"
prefix = "sim:mtr1"

galil = EpicsMotorGalil(f"{prefix}", name='galil')
galil_val = EpicsSignal(f'{prefix}.VAL', name='galil_val', auto_monitor=True)
galil_rbv = EpicsSignalRO(f'{prefix}.RBV', name='galil_rbv', auto_monitor=True)

prefix = "TEST{ION:PS}"
ION_Pump_PS = ION_Pump_PS(prefix, name="ION_Pump_PS")

RE = RunEngine({})

# bec = BestEffortCallback()
# RE.subscribe(bec)
RE.waiting_hook = ProgressBarManager()

register_custom_instructions(re=RE)

devices = {
    "galil": galil, "galil_val": galil_val, "galil_rbv": galil_rbv, "ION_Pump_PS": ION_Pump_PS
}

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

    for k, v in interpreter.logged_signals.items():
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
