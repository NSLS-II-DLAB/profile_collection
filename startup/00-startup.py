# Set environment variables, e.g add the following to .bashrc
#   export EPICS_CA_AUTO_ADDR_LIST=NO
#   export EPICS_CA_ADDR_LIST="172.17.255.255 127.0.0.1"
#
# Start simulated motor IOC before running the code (requires sudo).
# Refer to docker documentation on how to maintain downloaded images.
#   docker pull dchabot/simioc
#   sudo docker run --network="host" -d dchabot/simioc
#   sudo docker exec -it <ID> bash
# Inside the container shell
#   caRepeater &
#   telnet localhost 2048
# Run the code
#   ipython
#   run -i "startup/00-startup.py <args>"


import os
from datetime import datetime

import bluesky.preprocessors as bp
from bluesky.run_engine import RunEngine
from bluesky.utils import ProgressBarManager
from megatron_controls.interpreter import MegatronInterpreter
from megatron_controls.support import EpicsMotorGalil, ION_Pump_PS, register_custom_instructions
from ophyd import EpicsSignal, EpicsSignalRO

script_dir = os.environ.get("SCRIPT_DIRECTORY_PATH", "../scripts")
logging_dir = "./logs"
log_file_name = None

script_dir = os.path.abspath(os.path.expanduser(script_dir))
logging_dir = os.path.abspath(os.path.expanduser(logging_dir))

log_file_name = log_file_name or datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"

os.makedirs(logging_dir, exist_ok=True)
log_file_path = os.path.join(logging_dir, log_file_name)

prefix = "Test{DMC:1}A"

galil = EpicsMotorGalil(f"{prefix}", name="galil")
galil_val = EpicsSignal(f"{prefix}.VAL", name="galil_val", auto_monitor=True)
galil_rbv = EpicsSignalRO(f"{prefix}.RBV", name="galil_rbv", auto_monitor=True)

galil.wait_for_connection()
galil_val.wait_for_connection()
galil_rbv.wait_for_connection()

prefix = "Depo{PS:1}"
ION_Pump_PS = ION_Pump_PS(prefix, name="ION_Pump_PS")

devices = {"galil": galil, "galil_val": galil_val, "galil_rbv": galil_rbv, "ION_Pump_PS": ION_Pump_PS}

RE = RunEngine({})
RE.waiting_hook = ProgressBarManager()

register_custom_instructions(re=RE)

interpreter = MegatronInterpreter(
    devices=devices,
    script_dir=script_dir,
    logging_dir=logging_dir,
    log_file_path=log_file_path
)

@bp.reset_positions_decorator([galil.velocity])
def run_script(script_name):
    yield from interpreter.run_script(script_name)
