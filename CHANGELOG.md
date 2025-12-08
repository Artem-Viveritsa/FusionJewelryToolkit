# Changelog

All notable changes to this project will be documented in this file.

## [0.8.4] - 2025-12-08

### Changed
- Moved commands back to the Solid → Create panel from the dedicated "Jewelry Toolkit" custom toolbar panel due to UI bugs where other interface elements disappeared.

## [0.8.3] - 2025-12-08

### Fixed
- Fixed girdle thickness calculation in CuttersForGemstones command.

## [0.8.2] - 2025-12-08

### Changed
- Updated icon for ObjectsRefold command.

## [0.8.1] - 2025-12-08

### Changed
- Refactored attributes system: Consolidated individual attributes into a single JSON-based properties attribute for better organization and performance.
- Updated all command modules to use the new properties-based attribute system.


## [0.8.0] - 2025-12-07

### Added
- **SurfaceUnfold** (Early Preview): Unfold curved surfaces or meshes to flat 2D sketches for pattern creation and manufacturing.
- **ObjectsRefold** (Early Preview): Refold any BRep bodies back onto curved surfaces with automatic body wrapping.

### Changed
- Major UI restructure: Moved all commands from Solid → Create panel to a dedicated \"Jewelry Toolkit\" custom toolbar panel for better organization.
- Updated all command modules to support the new custom panel architecture.
- All gemstone and prong commands now support selecting construction planes in addition to BRep faces.

### Note
- SurfaceUnfold and ObjectsRefold are currently in **Early Preview** status. These features are experimental and may have limitations or bugs. User feedback is welcome!

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