# Changelog

All notable changes to this project will be documented in this file.

## [0.9.6] - 2026-02-06

### Added
- Negative offset support for `GemstonesOnFaceAtCurve` and `GemstonesOnFaceBetweenCurves` commands. Curve extrapolation allows gemstone placement beyond curve endpoints along the tangent direction for flexible gemstone distribution.

### Changed
- `Curves.py`: Implemented curve extrapolation for `calculatePointsAndSizesAlongCurve()` using tangent vectors at curve endpoints. Negative offsets now extend placement area without clipping at curve boundaries.
- `Curves.py`: Implemented polyline extrapolation for `calculatePointsAndSizesBetweenCurves()` with size consistency. Gemstones placed outside polyline bounds maintain the size of the nearest edge gemstone on the curves.
- Removed validation restrictions preventing negative offset values in both gemstone placement commands.

## [0.9.5] - 2025-12-19

### Added
- `Gemstones.py`: New `isGemstone()` helper function to identify gemstone bodies by attributes or geometry analysis. Checks for gemstone attribute first, then performs geometry analysis looking for a single planar top face and cylindrical girdle face.
- `GemstonesInfo`: Enhanced with interactive selection input to choose specific gemstones for detailed information display. Supports showing info for all gemstones or selected subset.

### Changed
- Refactored gemstone body validation in `CuttersForGemstones`, `ProngsBetweenGemstones`, and `ChannelsBetweenGemstones` to use the new `isGemstone()` function, reducing code duplication and improving maintainability.
- `GemstonesInfo`: Converted from overlay-based visualization to command dialog with dynamic gemstone size summary display and selection filtering.

## [0.9.4] - 2025-12-17

### Added
- Added **Flip Face Normal** parameter to all gemstone placement commands (`GemstonesOnFaceAtPoints`, `GemstonesOnFaceAtCircles`, `GemstonesOnFaceAtCurve`, `GemstonesOnFaceBetweenCurves`) to rotate gemstones 180° around the face normal for better orientation control.

### Changed
- Renamed "Flip (orientation)" parameter to "Flip Gemstones" across all gemstone commands for clarity.

### Fixed
- Added backward compatibility handling in `EditExecuteHandler` for older custom features missing the new flipFaceNormal parameter to prevent runtime errors.

## [0.9.3] - 2025-12-15

### Changed
- Optimized custom feature update mechanism across all commands by removing redundant `updateFeature()` calls in edit handlers.
- Improved `ObjectsRefold` to preserve body attributes, materials, and names when refolding bodies onto surfaces.

### Added
- `Bodies.py`: New `copyAttributes()` helper function to copy attributes, appearance, material, and name between bodies.

### Fixed
- Enhanced `interpolateDataInPointTriangles()` in `Surface.py` to use inverse distance weighting for more accurate position and normal interpolation in edge cases.

## [0.9.2] - 2025-12-09

### Added
- `GemstonesOnFaceAtCurve`: Added **Uniform Distribution** parameter to distribute gemstones evenly along the curve without gaps at the ends.
- `GemstonesOnFaceBetweenCurves`: Added **Uniform Distribution** parameter to distribute gemstones evenly between curves without gaps at the ends.
- `GemstonesOnFaceBetweenCurves`: Refactored curve selection to use a single input accepting both curves at once, improving user experience.

### Changed
- `Curves.py`: Refactored calculation functions to support uniform distribution mode for both curve-based gemstone placement algorithms.

### Fixed
- `GemstonesOnFaceAtCurve`: Fixed compatibility with nonlinear interpolation parameters during feature editing.

## [0.9.1] - 2025-12-09

### Changed
- `GemstonesInfo`: Updated to display a summary list of gemstone sizes with total counts in the command dialog, sorted from smallest to largest diameter.

## [0.9.0] - 2025-12-09

### Added
- `GemstonesInfo`: new utility that overlays detected gemstone diameters as on-model text for quick inspection.

### Changed
- Moved the add-in's commands panel to the `Utilities` tab (previously in Solid → Create) to improve discoverability and reduce UI conflicts.

## [0.8.5] - 2025-12-08

### Added
- `SurfaceUnfold` now support selecting a construction plane for unfolding surfaces to custom planes instead of only the XY plane.
- Added X and Y offset parameters to `SurfaceUnfold` for positioning the unfolded sketch on the construction plane.

### Fixed
- Improved error handling in custom feature operations to ensure base features are properly finished even when errors occur.

## [0.8.4] - 2025-12-08

### Changed
- Moved commands back to the Solid → Create panel from the dedicated "Jewelry Toolkit" custom toolbar panel due to UI bugs where other interface elements disappeared.

## [0.8.3] - 2025-12-08

### Fixed
- Fixed girdle thickness calculation in `CuttersForGemstones` command.

## [0.8.2] - 2025-12-08

### Changed
- Updated icon for `ObjectsRefold` command.

## [0.8.1] - 2025-12-08

### Changed
- Refactored attributes system: Consolidated individual attributes into a single JSON-based properties attribute for better organization and performance.
- Updated all command modules to use the new properties-based attribute system.


## [0.8.0] - 2025-12-07

### Added
- `SurfaceUnfold` (Early Preview): Unfold curved surfaces or meshes to flat 2D sketches for pattern creation and manufacturing.
- `ObjectsRefold` (Early Preview): Refold any BRep bodies back onto curved surfaces with automatic body wrapping.

### Changed
- Major UI restructure: Moved all commands from Solid → Create panel to a dedicated \"Jewelry Toolkit\" custom toolbar panel for better organization.
- Updated all command modules to support the new custom panel architecture.
- All gemstone and prong commands now support selecting construction planes in addition to BRep faces.

### Note
- `SurfaceUnfold` and `ObjectsRefold` are currently in **Early Preview** status. These features are experimental and may have limitations or bugs. User feedback is welcome!

## [0.7.3] - 2025-12-01

### Changed
- Numerous UI improvements including field reordering and separators in various commands for better user experience.

## [0.7.2] - 2025-12-01

### Fixed
- Resolved issue with `getCurve3D` function not correctly retrieving curve geometry from certain selection types.

## [0.7.1] - 2025-11-29

### Added
- `GemstonesOnFaceAtPoints` now supports selecting vertices and construction points in addition to sketch points.
- `GemstonesOnFaceAtCurve` and `GemstonesOnFaceBetweenCurves` now support selecting BRep edges (e.g., model edges) in addition to sketch curves.

### Changed
- Refactored `createGemstone()` to remove `resourcesFolder` parameter; now uses `constants.ASSETS_FOLDER` for gemstone model path.
- Updated `calculatePointsAndSizesAlongCurve()` to accept `Curve3D` directly instead of SketchCurve for better flexibility.
- Updated `calculatePointsAndSizesBetweenCurves()` to work with `Curve3D` geometry instead of SketchCurve for improved API consistency.

### Fixed
- Improved robustness of point geometry extraction across different selection types.

## [0.7.0] - 2025-11-29

### Added
- New command `GemstonesOnFaceBetweenCurves` for placing gemstones between two sketch curves with automatic sizing based on curve distance.
- Enhanced `calculatePointsAndSizesAlongCurve` function with support for nonlinear interpolation for complex gemstone sizing patterns.
- New helper function `calculatePointsAndSizesBetweenCurves` for computing gemstone positions and sizes between two curves.
- Added `minimumGemstoneSize` constant to ensure minimum gemstone size constraints across all commands.

### Changed
- Updated constants module to include `measureManager` and `minimumGemstoneSize` for better size management.
- Improved gemstone size calculation to respect minimum size constraints in `GemstonesOnFaceAtCurve` and other commands.
- Enhanced numerical stability in distance calculations between curve positions.

## [0.6.4] - 2025-11-25

### Added
- Added `Flip Curve` parameter to `GemstonesOnFaceAtCurve` command for reversing gemstone placement direction along the curve.
- Enhanced `calculatePointsAndSizesAlongCurve` function with optimization for constant-size gemstone placement.

## [0.6.3] - 2025-11-24

### Fixed
- Fix access to curve geometry in `calculatePointsAndSizesAlongCurve`

## [0.6.2] - 2025-11-24

### Fixed
- Fix for getting point on curve at correct parameter in `calculatePointsAndSizesAlongCurve`

## [0.6.1] - 2025-11-24

### Fixed
- Fix ProngsOnFaceAtPoints default size and height values

## [0.6.0] - 2025-11-23

### Added
- GemstonesOnFaceAtCurve: Place gemstones along sketch curves with variable sizes and configurable spacing.

## [0.5.1] - 2025-11-21

### Added
- Now uses custom `Jewelry Material Library.adsklib` instead of Fusion's standard material library.

## [0.5.0] - 2025-11-20

### Added
- Added option for `CuttersForGemstones` to configure the cutter bottom type (Hole, Cone, Hemisphere).

## [0.4.0] - 2025-11-14

### Added
- GemstonesOnFaceAtCircles: Create round gemstones on a face at sketch circles.

### Changed
- Refactored gemstone creation functions into shared helpers/Gemstones.py module.


## [0.3.0] - 2025-11-08

### Added
- ProngsBetweenGemstones: Create prong bodies between gemstones.
- ChannelsBetweenGemstones: Create channels between gemstones.

### Changed
- Updated tool icons for improved visual clarity.
- Improved round-cut gemstone model for better accuracy.
- Added new parameters to GemstonesOnFaceAtPoints command (breaking change):
  - Absolute Depth Offset
  - Relative Depth Offset

## [0.2.0] - 2025-11-05
- Initial release of Fusion Jewelry Toolkit add-in for Fusion 360.