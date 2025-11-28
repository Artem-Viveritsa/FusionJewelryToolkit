from .commands.GemstonesOnFaceAtPoints import GemstonesOnFaceAtPoints
from .commands.GemstonesOnFaceAtCircles import GemstonesOnFaceAtCircles
from .commands.GemstonesOnFaceAtCurve import GemstonesOnFaceAtCurve
from .commands.GemstonesOnFaceBetweenCurves import GemstonesOnFaceBetweenCurves

from .commands.ProngsOnFaceAtPoints import ProngsOnFaceAtPoints
from .commands.ProngsBetweenGemstones import ProngsBetweenGemstones

from .commands.ChannelsBetweenGemstones import ChannelsBetweenGemstones
from .commands.CuttersForGemstones import CuttersForGemstones

commands = [
    GemstonesOnFaceAtPoints,
    GemstonesOnFaceAtCircles,
    GemstonesOnFaceAtCurve,
    GemstonesOnFaceBetweenCurves,
    
    ProngsOnFaceAtPoints,
    ProngsBetweenGemstones,
    
    ChannelsBetweenGemstones,
    CuttersForGemstones,
    ]

def run(context):
    for command in commands:
        command.run(context)


def stop(context):
    for command in commands:
        command.stop(context)