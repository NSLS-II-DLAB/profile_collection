import re
from datetime import datetime
import os
import asyncio
from types import SimpleNamespace
import shlex

from bluesky.utils import make_decorator
import bluesky.plan_stubs as bps

from .support import wait_for_condition, motor_move, motor_stop, motor_home


_device_mapping = {
    "Galil RBV": "galil_rbv",
    "Galil VAL": "galil_val"
}

_required_devices = ("galil", "galil_val", "galil_rbv")

class Interpreter:

    # sp - speed
    # pa - position absolute
    # pr - position relative
    # bg - begin (no argument)
    # t60 - pause 60 seconds
    # st - stop motor ???
    # waitai - wait for condition (Analog Input)
    # waitdi - wait for condition (Digital Input)

    def __init__(self, *, devices):

        # Validate devices
        for device in _required_devices:
            if device not in devices:
                raise RuntimeError(f"Device {device} is missing in the devices list")

        self.devices = SimpleNamespace(**devices)
        self.galil_abs_rel = 0  # 0 - absolute, 1 - relative
        self.galil_pos = 0
        self.galil_speed = 1000000

        self.logged_signals = {}

    def _process_line(self, code_line, *, scan_for_logs=False):
        # TODO: Modify the parsing algorithm to properly handle quoted strings with spaces

        # Remove comments
        code_line = re.sub(r"#.*$", "", code_line)
        code_line = code_line.strip(" ")

        ss_full = [shlex.split(_) for _ in code_line.split(",")]
        ss = []
        for _ in ss_full:
            ss.extend(_)
        ss = [_.strip(" ") for _ in ss]

        if ss:
            if scan_for_logs:
                if ss[0] == "log" and len(ss) == 2:
                    print(f"Adding variable to the log")
                    yield from self._log(ss[1:])
            else:
                if re.search(r"^t\d+$", ss[0]) and len(ss) == 1:
                    _ = int(ss[0][1:])
                    print(f"Pause: {_} s")
                    yield from bps.sleep(_)
                elif ss[0] == "sp" and len(ss) == 2 and re.search(f"^\d+$", ss[1]):
                    _ = int(ss[1])
                    print(f"Set speed: {_}")
                    yield from self._galil_set_speed(_)
                elif ss[0] == "pa" and len(ss) == 2 and re.search(f"^-*\d+$", ss[1]):
                    _ = int(ss[1])
                    print(f"Set absolute position: {_}")
                    yield from self._galil_set_abs_pos(_)
                elif ss[0] == "pr" and len(ss) == 2 and re.search(f"^-*\d+$", ss[1]):
                    _ = int(ss[1])
                    print(f"Set relative position: {_}")
                    yield from self._galil_set_rel_pos(_)
                elif ss[0] == "bg" and len(ss) == 1:
                    print(f"Begin")
                    yield from self._galil_begin()
                elif ss[0] == "st" and len(ss) == 1:
                    print(f"Stop motor")
                    yield from self._galil_stop()
                elif ss[0] == "hm" and len(ss) == 1:
                    print(f"Home motor")
                    yield from self._galil_home()
                elif ss[0] == "waitai" and len(ss) >= 4 and len(ss) <= 6:
                    print(f"Wait for condition (Analog Input)")
                    yield from self._waitai(ss[1:])
                elif ss[0] == "waitdi" and len(ss) >= 3 and len(ss) <= 4:
                    print(f"Wait for condition (Digital Input)")
                    yield from self._waitdi(ss[1:])
                elif ss[0] == "log" and len(ss) == 2:
                    yield from bps.null()
                else:
                    raise RuntimeError(f"Invalid code line: {code_line!r} ({ss})")
        else:
            print("Skipping the empty line")
            yield from bps.null()

    def _galil_set_speed(self, speed):
        self.galil_speed = speed
        yield from bps.null()

    def _galil_set_abs_pos(self, pos):
        self.galil_abs_rel = 0
        self.galil_pos = pos
        yield from bps.null()

    def _galil_set_rel_pos(self, pos):
        self.galil_abs_rel = 1
        self.galil_pos = pos
        yield from bps.null()

    def _galil_begin(self):
        yield from bps.mv(self.devices.galil.velocity, self.galil_speed/1000000)
        yield from bps.checkpoint()
        yield from motor_move(self.devices.galil, self.galil_pos/1000000, is_rel=self.galil_abs_rel)

    def _galil_stop(self):
        yield from motor_stop(self.devices.galil)

    def _galil_home(self):
        yield from motor_home(self.devices.galil)

    def _waitai(self, params):
        source = params[0]
        operator = params[1]
        value = float(params[2])
        tolerance, timeout = 0, None
        if len(params) >= 4:
            tolerance = float(params[3])
        if len(params) >= 5:
            timeout = float(params[4])

        if source in _device_mapping:
            device_name = _device_mapping[source]
            signal = getattr(self.devices, device_name)
        else:
            raise RuntimeError(f"Unrecognized device name: {source!r}")

        yield from wait_for_condition(
            signal=signal, target=value/1000000, operator=operator, tolerance=tolerance, timeout=timeout
        )

    def _waitdi(self, params):
        source = params[0]
        value = int(params[1])
        timeout = None
        if len(params) >= 3:
            timeout = float(params[2])

        if source in _device_mapping:
            device_name = _device_mapping[source]
            signal = getattr(self.devices, device_name)
        else:
            raise RuntimeError(f"Unrecognized device name: {source!r}")

        signal = self.devices.galil_signal
        yield from wait_for_condition(
            signal=signal, target=value/1000000, operator="==", tolerance=0, timeout=timeout
        )

    def _log(self, params):
        source = params[0]
        self.logged_signals[source] = getattr(self.devices, _device_mapping[source])
        yield from bps.null()



def ts_periodic_logging_wrapper(plan, signals, log_file_path, period=1):

    stop = asyncio.Event()

    async def logging_coro():
        while not stop.is_set():
            is_new_file = False
            if not os.path.isfile(log_file_path):
                dir, _ = os.path.split(log_file_path)
                os.makedirs(dir, exist_ok=True)
                is_new_file = True

            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")

            with open(log_file_path, "at") as f:
                if is_new_file:
                    s = ",".join([f"\"{_}\"" for _ in signals.keys()])
                    f.write(f"Timestamp,{s}\n")
                s = ",".join([f"{_.value}" for _ in signals.values()])
                f.write(f"{timestamp},{s}\n")

            await asyncio.sleep(period)

    class StartStopLogging(object):

        def __enter__(self):
            print(f"Starting periodic logging")
            asyncio.ensure_future(logging_coro())

        def __exit__(self, *args):
            print(f"Stopping periodic logging")
            stop.set()

    def _inner():
        with StartStopLogging():
            yield from plan

    return (yield from _inner())


ts_periodic_logging_decorator = make_decorator(ts_periodic_logging_wrapper)
