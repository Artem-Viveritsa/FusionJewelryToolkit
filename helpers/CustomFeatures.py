from typing import Optional

import adsk.fusion


def getBaseFeature(customFeature: adsk.fusion.CustomFeature) -> Optional[adsk.fusion.BaseFeature]:
    """Return the base feature owned by a custom feature.

    Args:
        customFeature: The custom feature to inspect.

    Returns:
        The owned base feature or None.
    """
    for feature in customFeature.features:
        if feature.objectType == adsk.fusion.BaseFeature.classType():
            return adsk.fusion.BaseFeature.cast(feature)

    return None
