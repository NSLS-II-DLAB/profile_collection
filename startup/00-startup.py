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


import argparse
import os
from datetime import datetime

import bluesky.preprocessors as bp
from bluesky.run_engine import RunEngine
from bluesky.utils import ProgressBarManager
from megatron.context import create_shared_context
from megatron.interpreter import MegatronInterpreter
from megatron.logger import ts_periodic_logging_decorator
from megatron.support import EpicsMotorGalil, register_custom_instructions
from ophyd import EpicsSignal, EpicsSignalRO

parser = argparse.ArgumentParser(
    description=(
        "Startup script for the Megatron interpreter. " "Run scripts with logging in an EPICS environment."
    )
)
parser.add_argument(
    "-s",
    "--script-dir",
    type=str,
    default=".",
    help="Directory containing the scripts to run. Defaults to the current directory.",
)
parser.add_argument(
    "-l",
    "--logging-dir",
    type=str,
    default="./logs",
    help="Directory to store log files. Defaults to './logs' in the current directory.",
)
parser.add_argument(
    "-f",
    "--log-file-name",
    type=str,
    default=None,
    help="Custom log file name. Defaults to a timestamp-based name.",
)
parser.add_argument(
    "-m",
    "--use-sim-motor",
    action="store_true",
    help="Use the simulated motor (sim:mtr1). Defaults to the real motor (Test{DMC:1}A).",
)

args = parser.parse_args()

prefix = "sim:mtr1" if args.use_sim_motor else "Test{DMC:1}A"

script_dir = args.script_dir
logging_dir = args.logging_dir
log_file_name = args.log_file_name or datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"

os.makedirs(logging_dir, exist_ok=True)
log_file_path = os.path.join(logging_dir, log_file_name)

galil = EpicsMotorGalil(f"{prefix}", name="galil")
galil_val = EpicsSignal(f"{prefix}.VAL", name="galil_val", auto_monitor=True)
galil_rbv = EpicsSignalRO(f"{prefix}.RBV", name="galil_rbv", auto_monitor=True)

galil.wait_for_connection()
galil_val.wait_for_connection()
galil_rbv.wait_for_connection()

devices = {"galil": galil, "galil_val": galil_val, "galil_rbv": galil_rbv}

RE = RunEngine({})
RE.waiting_hook = ProgressBarManager()

register_custom_instructions(re=RE)

context = create_shared_context(devices)
interpreter = MegatronInterpreter(shared_context=context)


@bp.reset_positions_decorator([galil.velocity])
@ts_periodic_logging_decorator(signals=context.logged_signals, log_file_path=log_file_path, period=1)
def run_with_logging(script_path):
    yield from interpreter.execute_script(script_path)
