import time
import numpy as np
import asyncio
import uuid

from bluesky import Msg
from ophyd import DeviceStatus
import bluesky.plan_stubs as bps


class _ConditionStatus(DeviceStatus):
    """
    Status object that waits for a variable to reach specified target value.
    The status object succeed when the specified condition is met.

    The object was created by modifying ``MoveStatus`` object from Ophyd library.
    TODO: Some features are not used, so some code can be removed in the future.

    Parameters
    ----------
    positioner : Positioner
    target : float
        Target position
    operator : str
        One of "<", "<=", ">", ">=", "==", "!=", "!="
    tolerance : float, optional
        Tolerance for the condition. Default is 0.
    """

    def __init__(self, signal, target, operator, *, tolerance=None, start_ts=None, **kwargs):
        self._tname = "timeout for {}".format(signal.name)
        if start_ts is None:
            start_ts = time.time()

        tolerance = tolerance or 0
        if tolerance < 0:
            tolerance = 0

        self.pos = signal
        self.target = target
        self.start_ts = start_ts
        self.start_pos = self.pos.position if hasattr(self.pos, "position") else self.pos.value
        self.finish_ts = None
        self.finish_pos = None

        self._unit = getattr(self.pos, "egu", None)
        self._precision = getattr(self.pos, "precision", None)
        self._name = self.pos.name

        # call the base class
        super().__init__(signal, **kwargs)

        def cb(*args, obj=None, sub_type=None, **kwargs):
            timestamp = kwargs.get("timestamp")
            value = kwargs.get("value")

            success = False
            if operator == "<":
               if value < target:
                   success = True
            elif operator == "<=":
               if value <= target:
                   success = True
            elif operator == ">":
                if value > target:
                     success = True
            elif operator == ">=":
                if value >= target:
                    success = True
            elif operator in ("=", "=="):
                if target - tolerance <= value <= target + tolerance:
                    success = True
            elif operator == "!=":
                if value <= target - tolerance or value >= target + tolerance:
                    success = True
            else:
                raise RuntimeError(f"Invalid operator: {operator!r}")

            if success:
                signal.clear_sub(cb)
                self.set_finished()

        if hasattr(signal, "SUB_READBACK"):
            event_type = signal.SUB_READBACK
        else:
            event_type = signal.SUB_VALUE
        signal.subscribe(cb, event_type=event_type)

        # Notify watchers (things like progress bars) of new values
        # at the device's natural update rate.
        if not self.done:
           self.pos.subscribe(self._notify_watchers, event_type=event_type)

    def watch(self, func):
        """
        Subscribe to notifications about partial progress.

        This is useful for progress bars.

        Parameters
        ----------
        func : callable
            Expected to accept the keyword aruments:

                * ``name``
                * ``current``
                * ``initial``
                * ``target``
                * ``unit``
                * ``precision``
                * ``fraction``
                * ``time_elapsed``
                * ``time_remaining``
        """
        def f(*args, unit=None, **kwargs):
            _unit = "unit"
            if isinstance(unit, str):
                _unit = unit
            func(*args, unit=_unit, **kwargs)

        self._watchers.append(f)

    def _notify_watchers(self, value, *args, **kwargs):
        # *args and **kwargs catch extra inputs from pyepics, not needed here
        if not self._watchers:
            return
        current = value
        target = self.target
        initial = self.start_pos
        time_elapsed = time.time() - self.start_ts
        try:
            fraction = np.clip(abs(target - current) / abs(initial - target), 0, 1)
        # maybe we can't do math?
        except (TypeError, ZeroDivisionError):
            fraction = None

        if fraction is not None and np.isnan(fraction):
            fraction = None

        for watcher in self._watchers:
            watcher(
                name=self._name,
                current=current,
                initial=initial,
                target=target,
                unit=self._unit,
                precision=self._precision,
                time_elapsed=time_elapsed,
                fraction=fraction,
            )

    @property
    def error(self):
        """Error between target position and current* position

        * If motion is already complete, the final position is used
        """
        if self.finish_pos is not None:
            finish_pos = self.finish_pos
        else:
            finish_pos = self.pos.position

        try:
            return np.array(finish_pos) - np.array(self.target)
        except Exception:
            return None

    def _settled(self):
        """Hook for when motion has completed and settled"""
        super()._settled()
        self.pos.clear_sub(self._notify_watchers)
        self._watchers.clear()
        self.finish_ts = time.time()
        self.finish_pos = self.pos.position if hasattr(self.pos, "position") else self.pos.value

    @property
    def elapsed(self):
        """Elapsed time"""
        if self.finish_ts is None:
            return time.time() - self.start_ts
        else:
            return self.finish_ts - self.start_ts

    def __str__(self):
        return (
            "{0}(done={1.done}, pos={1.pos.name}, "
            "elapsed={1.elapsed:.1f}, "
            "success={1.success}, settle_time={1.settle_time})"
            "".format(self.__class__.__name__, self)
        )

    __repr__ = __str__



def gen_set_condition(re):

    async def _inner(msg):
        signal = msg.kwargs['signal']
        target = msg.kwargs['target']
        operator = msg.kwargs['operator']
        tolerance = msg.kwargs.get('tolerance', None)
        group = msg.kwargs['group']

        pardon_failures = re._pardon_failures
        p_event = asyncio.Event(**re._loop_for_kwargs)
        ret = _ConditionStatus(signal=signal, target=target, operator=operator, tolerance=tolerance)

        def done_callback(status=None):
            #RE.log.debug("The object %r reports set is done with status %r", obj, ret.success)
            re._loop.call_soon_threadsafe(re._status_object_completed, ret, p_event, pardon_failures)

        try:
            ret.add_callback(done_callback)
        except AttributeError:
            # for ophyd < v0.8.0
            ret.finished_cb = done_callback

        re._groups[group].add(p_event.wait)
        re._status_objs[group].add(ret)


        return (ret,)

    return _inner


def register_custom_instructions(re):
    _set_condition = gen_set_condition(re=re)
    re.register_command('set_condition', _set_condition)


def wait_for_condition(signal, target, operator, tolerance=0, timeout=None):
    group = str(uuid.uuid4())
    yield Msg('set_condition', signal=signal, target=target, operator=operator, group=group)
    yield Msg("wait", None, group=group, timeout=timeout)


def motor_stop(motor):
    yield from bps.stop(motor)
    yield from bps.sleep(0.2)
    wait_for_condition(motor.motor_done_move, 1, "==")
    yield from bps.sleep(0.2)


def motor_move(motor, position, is_rel=False):
    yield from motor_channel_enable(motor)
    yield from motor_stop(motor)
    _set = bps.rel_set if is_rel else bps.abs_set
    yield from _set(motor, position, wait=False)

def motor_home(motor):
    yield from motor_channel_enable(motor)
    yield from motor_stop(motor)
    yield from bps.abs_set(motor.home_reverse, 1, wait=True)
    yield from wait_for_condition(motor.homing_monitor, 0, "==")


def motor_channel_enable(motor):
    yield from bps.abs_set(motor.channel_enable, 1, wait=True)
