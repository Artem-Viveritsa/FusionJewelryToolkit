COMPANY_NAME = 'Viveritsa'
ADDIN_NAME = 'FusionJewelryToolkit'

PREFIX = COMPANY_NAME + ADDIN_NAME

PANEL_ID = PREFIX + 'Panel'

GEMSTONES_ON_FACE_AT_POINTS = 'GemstonesOnFaceAtPoints'
GEMSTONES_ON_FACE_AT_CIRCLES = 'GemstonesOnFaceAtCircles'
PRONGS_ON_FACE_AT_POINTS = 'ProngsOnFaceAtPoints'
CUTTERS_FOR_GEMSTONES = 'CuttersForGemstones'
CHANNELS_BETWEEN_GEMSTONES = 'ChannelsBetweenGemstones'
PRONGS_BETWEEN_GEMSTONES = 'ProngsBetweenGemstones'

ENTITY = 'entity'

GEMSTONE = 'gemstone'
GEMSTONE_IS_FLIPPED = 'gemstoneIsFlipped'
GEMSTONE_RELATIVE_DEPTH_OFFSET = 'gemstoneRelativeDepthOffset'
GEMSTONE_ABSOLUTE_DEPTH_OFFSET = 'gemstoneAbsoluteDepthOffset'
GEMSTONE_CUT = 'gemstoneCut'
GEMSTONE_ROUND_CUT = 'round'

PRONG = 'prong'
CUTTER = 'cutter'
CHANNEL = 'channel'

class InputDef:
    def __init__(self, id: str, name: str, tooltip: str):
        self.id: str = id
        self.name: str = name
        self.tooltip: str = tooltip