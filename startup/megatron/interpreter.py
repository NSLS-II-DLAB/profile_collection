from bluesky import RunEngine, Msg
from ophyd import EpicsMotor, EpicsSignal, EpicsSignalWithRBV, EpicsSignalRO, DeviceStatus
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.utils import ProgressBarManager
import bluesky.preprocessors as bp
from types import SimpleNamespace

import bluesky.plan_stubs as bps

import re

from .support import wait_for_condition, motor_move, motor_stop


_required_devices = ("galil", "galil_signal")

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

    def _process_line(self, code_line):
        # TODO: Modify the parsing algorithm to properly handle quoted strings with spaces
        #       and ignore comments

        # Remove comments
        code_line = re.sub(r"#.*$", "", code_line)
        code_line = code_line.strip(" ")

        ss_full = re.split(r" |,", code_line)
        ss = []
        for _ in ss_full:
            _ = _.strip(" ")
            _ = _.strip(",")
            if _:
                ss.append(_)

        if ss:
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
            elif ss[0] == "waitai" and len(ss) >= 4 and len(ss) <= 6:
                print(f"Wait for condition (Analog Input)")
                yield from self._waitai(ss[1:])
            elif ss[0] == "waitdi" and len(ss) >= 3 and len(ss) <= 4:
                print(f"Wait for condition (Digital Input)")
                yield from self._waitdi(ss[1:])
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

    def _waitai(self, params):
        source = params[0]
        operator = params[1]
        value = float(params[2])
        tolerance, timeout = 0, None
        if len(params) >= 4:
            tolerance = float(params[3])
        if len(params) >= 5:
            timeout = float(params[4])

        # TODO: the 'source' is a string and should be properly handled.
        #    For now, let's assume it's always 'galil' object
        signal = self.devices.galil_signal
        yield from wait_for_condition(
            signal=signal, target=value/1000000, operator=operator, tolerance=tolerance, timeout=timeout
        )

    def _waitdi(self, params):
        source = params[0]
        value = int(params[1])
        timeout = None
        if len(params) >= 3:
            timeout = float(params[2])

        # TODO: the 'source' is a string and should be properly handled.
        #    For now, let's assume it's always 'galil' object
        signal = self.devices.galil_signal
        yield from wait_for_condition(
            signal=signal, target=value/1000000, operator="==", tolerance=0, timeout=timeout
        )
