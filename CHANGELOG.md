# Changelog

All notable changes to this project will be documented in this file.

## [0.6.4] - 2025-11-25

### Added
- Added `Flip Curve` parameter to `GemstonesOnFaceAtCurve` command for reversing gemstone placement direction along the curve.
- Enhanced `calculatePointsAndSizesAlongCurve` function with optimization for constant-size gemstone placement.

## [0.6.3] - 2025-11-25

### Fixed
- Fix access to curve geometry in `calculatePointsAndSizesAlongCurve`

## [0.6.2] - 2025-11-25

### Fixed
- Fix for getting point on curve at correct parameter in `calculatePointsAndSizesAlongCurve`

## [0.6.1] - 2025-11-25

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