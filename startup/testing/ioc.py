import numpy as np
import time
import textwrap
import random

from caproto import ChannelType
from caproto.server import PVGroup, SubGroup, ioc_arg_parser, pvproperty, run


class IonPumpPS(PVGroup):

    Pwr_I = pvproperty(
        value=0,
        name="Pwr-I",
        dtype=float,
        read_only=True,
        doc="ION Power"
    )

    I_I = pvproperty(
        value=0,
        name="I-I",
        dtype=float,
        read_only=True,
        doc="ION Current"
    )

    E_I = pvproperty(
        value=0,
        name="E-I",
        dtype=float,
        read_only=True,
        doc="ION Voltage"
    )

    Rate_Arc_I = pvproperty(
        value=0,
        name="Rate:Arc-I",
        dtype=float,
        read_only=True,
        doc="ION Arc Rate"
    )

    Cnt_Target_KwHr_RB = pvproperty(
        value=0,
        name="Cnt:TargetKwHr-RB",
        dtype=float,
        read_only=True,
        doc="ION KWH Count"
    )

    Enbl_Out_Cmd = pvproperty(
        value="Enable",
        name="Enbl:Out-Cmd",
        record="bo",
        enum_strings=["Enable", "Disable"],
        dtype=ChannelType.ENUM,
        read_only=False,
        doc="ION Output Enable"
    )

    @Enbl_Out_Cmd.putter
    async def Enbl_Out_Cmd(self, instance, value):
        return value

    @Enbl_Out_Cmd.scan(period=1.0)
    async def Enbl_Out_Cmd(self, instance, async_lib):
        enabled = instance.value == "Enable"
        _I_I = random.gauss(10, 1) if enabled else 0
        _E_I = random.gauss(400, 1) if enabled else 0
        _Pwr_I = _I_I * _E_I
        _Rate_Arc_I = random.gauss(10, 1) if enabled else 0

        _kwhr = 0.01 if enabled else 0
        _Cnt_Target_KwHr_RB = self.Cnt_Target_KwHr_RB.value + _kwhr

        await self.I_I.write(value=_I_I)
        await self.E_I.write(value=_E_I)
        await self.Pwr_I.write(value=_Pwr_I)
        await self.Rate_Arc_I.write(value=_Rate_Arc_I)
        await self.Cnt_Target_KwHr_RB.write(value=_Cnt_Target_KwHr_RB)


class MegatronSim(PVGroup):
    """
    Simulation of Megatron PVs

    Starting the IOC:

        python ioc.py --list-pvs  (uses the default prefix 'TEST')

        python ioc.py --list-pvs --prefix="REAL-IOC"

    """

    ion_pump_power = SubGroup(IonPumpPS, prefix="{{ION:PS}}", doc="Ion pump power supply")

if __name__ == "__main__":
    ioc_options, run_options = ioc_arg_parser(
        default_prefix="TEST",
        desc=textwrap.dedent(MegatronSim.__doc__),
    )

    ioc = MegatronSim(**ioc_options)
    run(ioc.pvdb, **run_options)
