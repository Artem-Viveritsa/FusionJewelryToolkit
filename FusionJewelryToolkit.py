from .commands.GemstonesOnFaceAtPoints import GemstonesOnFaceAtPoints
from .commands.ProngsOnFaceAtPoints import ProngsOnFaceAtPoints
from .commands.Cutters import Cutters

commands = [
    GemstonesOnFaceAtPoints,
    ProngsOnFaceAtPoints,
    Cutters
    ]

def run(context):
    for command in commands:
        command.run(context)


def stop(context):
    for command in commands:
        command.stop(context)