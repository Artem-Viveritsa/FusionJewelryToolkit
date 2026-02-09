import os, adsk.core, adsk.fusion

app = adsk.core.Application.get()
measureManager = app.measureManager

zeroPoint = adsk.core.Point3D.create(0, 0, 0)
xVector = adsk.core.Vector3D.create(1, 0, 0)
yVector = adsk.core.Vector3D.create(0, 1, 0)
zVector = adsk.core.Vector3D.create(0, 0, 1)

ASSETS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', '')

materialLibrary = adsk.core.Application.get().materialLibraries.load(ASSETS_FOLDER + 'Jewelry Material Library.adsklib')

minimumGemstoneSize = 0.05
gemstoneOverlapMergeThreshold = 0.01