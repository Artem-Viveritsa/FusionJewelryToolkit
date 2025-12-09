# Fusion 360 Jewelry Toolkit

A small collection of utilities that speed up jewelry modeling in Fusion 360. The add-in adds specialized commands for gemstone placement, prong creation, channels, cutters, and surface manipulation.

[![Gemstones icon](commands/GemstonesOnFaceAtPoints/resources/32x32@2x.png)](#gemstonesonfaceatpoints--place-round-gemstones-on-a-face-at-specified-points) [![Gemstones icon](commands/GemstonesOnFaceAtCircles/resources/32x32@2x.png)](#gemstonesonfaceatcircles--place-round-gemstones-on-a-face-at-sketch-circles) [![Gemstones icon](commands/GemstonesOnFaceAtCurve/resources/32x32@2x.png)](#gemstonesonfaceatcurve--place-gemstones-along-a-curve-with-variable-sizes) [![Gemstones icon](commands/GemstonesOnFaceBetweenCurves/resources/32x32@2x.png)](#gemstonesonfacebetweencurves--place-gemstones-between-two-curves) [![Prongs icon](commands/ProngsOnFaceAtPoints/resources/32x32@2x.png)](#prongsonfaceatpoints--generate-prongs-on-a-face-at-specified-points) [![ProngsBetweenGemstones icon](commands/ProngsBetweenGemstones/resources/32x32@2x.png)](#prongsbetweengemstones--create-prongs-between-gemstones) [![ChannelsBetweenGemstones icon](commands/ChannelsBetweenGemstones/resources/32x32@2x.png)](#channelsbetweengemstones--create-channels-between-gemstones) [![CuttersForGemstones icon](commands/CuttersForGemstones/resources/32x32@2x.png)](#cuttersforgemstones--create-cutter-bodies-for-gemstone-seating) [![SurfaceUnfold icon](commands/SurfaceUnfold/resources/32x32@2x.png)](#surfaceunfold--unfold-curved-surfaces-to-flat-2d-sketches-early-preview) [![ObjectsRefold icon](commands/ObjectsRefold/resources/32x32@2x.png)](#objectsrefold--refold-flat-patterns-onto-curved-surfaces-early-preview) [![Gemstones Info icon](commands/GemstonesInfo/resources/32x32@2x.png)](#gemstonesinfo--show-detected-gemstone-diameters-on-model-early-preview)


## Installation
1. In Fusion 360, go to Utilities → Add-ins → Scripts and Add-ins.
2. Click the `+` button and choose "Script or Add-in from my computer".
3. Select the `FusionJewelryToolkit` folder and click Open.
4. To make the add-in run automatically when Fusion starts, enable the "Run on Startup" checkbox.
5. After installation, the commands will appear in the Utilities tab instead of the Solid → Create panel.

Note: This add-in uses the Custom Feature Fusion API, which is currently in preview. Future Fusion 360 updates may require changes to the add-in.

## What's new
- **Enhanced Gemstone Placement:**
  - Added **Uniform Distribution** parameter to `GemstonesOnFaceAtCurve` and `GemstonesOnFaceBetweenCurves` for even spacing without end gaps.
  - Improved `GemstonesOnFaceBetweenCurves` UI with streamlined curve selection.
- **GemstonesInfo improvements:**
  - Fixed text rendering with proper billboarding for better visibility from all angles.
  - Enhanced dialog display to properly show all gemstone size summaries.
- **UI change:**
    - Moved commands panel to the `Utilities` tab to improve discoverability and avoid conflicts with Solid → Create.
- **Enhanced SurfaceUnfold and ObjectsRefold:**
  - Added support for selecting construction planes (not just XY plane) for unfolding surfaces
  - Added X and Y offset parameters to position unfolded sketches on construction planes
  - ⚠️ **Note**: These features are experimental and in early preview stage. Feedback welcome!
- See [full changelog](CHANGELOG.md) for complete version history.

---

![Gemstones icon](commands/GemstonesOnFaceAtPoints/resources/32x32@2x.png)
## GemstonesOnFaceAtPoints — Place round gemstones on a face at specified points
- **Description:** Creates round-cut gemstone bodies at selected points on a chosen face or construction plane. Supports sketch points, vertices, and construction points.
- **Selection:** 1 face or construction plane and one or more points (sketch points, vertices, or construction points). The face/plane may have any curvature or complexity; the points do not need to lie directly on the face/plane.
- **Key parameters:**
  - **Size** — Gemstone diameter. Default: `1.5 mm`. Determines the overall size of the gemstone.
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: `false`.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

![Gemstones icon](commands/GemstonesOnFaceAtCircles/resources/32x32@2x.png)
## GemstonesOnFaceAtCircles — Place round gemstones on a face at sketch circles
- **Description:** Creates round-cut gemstone bodies at selected sketch circles on a chosen face or construction plane. The gemstone size matches the circle diameter.
- **Selection:** 1 face or construction plane and one or more sketch circles. The face/plane may have any curvature or complexity; the circles do not need to lie directly on the face/plane. Minimum circle diameter is `0.5 mm`.
- **Key parameters:**
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: `false`.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

![Gemstones icon](commands/GemstonesOnFaceAtCurve/resources/32x32@2x.png)
## GemstonesOnFaceAtCurve — Place gemstones along a curve with variable sizes
- **Description:** Creates round-cut gemstone bodies along a selected curve (sketch curve or model edge) on a chosen face or construction plane. Gemstone sizes can gradually change from start to end.
- **Selection:** 1 face or construction plane and 1 curve (sketch curve or edge).
- **Key parameters:**
  - **Start Offset** — Distance from the curve start to the first gemstone. Default: `0 mm`.
  - **End Offset** — Distance from the curve end to the last gemstone. Default: `0 mm`.
  - **Flip Curve** — Flip gemstone placement direction. Starts placing gemstones from the opposite end of the curve. Default: `false`.
  - **Start Size** — Gemstone diameter at the curve start. Default: `1.0 mm`. Minimum: `0.5 mm`.
  - **End Size** — Gemstone diameter at the curve end. Default: `0.7 mm`. Minimum: `0.5 mm`.
  - **Size Step** — Size discretization step. Gemstone sizes are rounded to multiples of this value. Default: `0.05 mm`. Range: `0–1.0 mm`.
  - **Target Gap** — Target distance between adjacent gemstones along the curve. Default: `0.1 mm`.
  - **Uniform Distribution** — Distribute gemstones uniformly along the curve. Ensures gemstones fill the entire available length from start offset to end offset without gaps at the ends. Default: `false`.
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: `false`.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

![Gemstones icon](commands/GemstonesOnFaceBetweenCurves/resources/32x32@2x.png)
## GemstonesOnFaceBetweenCurves — Place gemstones between two curves
- **Description:** Creates round-cut gemstone bodies along a path between two selected curves (sketch curves or model edges) on a chosen face or construction plane. Gemstone sizes are automatically determined by the distance between the two curves.
- **Selection:** 1 face or construction plane and 2 curves (sketch curves or edges). The curves should be approximately the same length for best results.
- **Key parameters:**
  - **Start Offset** — Distance from the start of the curves to the first gemstone. Default: `0 mm`.
  - **End Offset** — Distance from the end of the curves to the last gemstone. Default: `0 mm`.
  - **Flip Direction** — Flip gemstone placement direction. Starts placing gemstones from the opposite end of the curves. Default: `false`.
  - **Uniform Distribution** — Distribute gemstones uniformly along the curves. Ensures gemstones fill the entire available length from start offset to end offset without gaps at the ends. Default: `false`.
  - **Size Ratio** — Multiplier for gemstone size based on curve distance. Default: `1.0`. Range: `0.5–2.0`.
  - **Size Step** — Size discretization step. Gemstone sizes are rounded to multiples of this value. Default: `0.05 mm`. Range: `0–1.0 mm`.
  - **Target Gap** — Target distance between adjacent gemstones along the curve path. Default: `0.1 mm`.
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: `false`.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

---
![Prongs icon](commands/ProngsOnFaceAtPoints/resources/32x32@2x.png)
## ProngsOnFaceAtPoints — Generate prongs on a face at specified points
- **Description:** Generates prong bodies at selected sketch points on a chosen face or construction plane.
- **Selection:** 1 face or construction plane and one or more sketch points. The face/plane may have any curvature or complexity; the points do not need to lie directly on the face/plane.
- **Key parameters:**
  - **Size (prong base diameter)** — Default: `0.4 mm`. Minimum: `0.1 mm`.
  - **Height (prong height)** — Height above the face. Default: `0.4 mm`. Minimum: `0.1 mm`.

---

![ProngsBetweenGemstones icon](commands/ProngsBetweenGemstones/resources/32x32@2x.png)
## ProngsBetweenGemstones — Create prongs between gemstones
- **Description:** Creates prongs at the midpoint between nearby gemstones based on distance constraint.
- **Selection:** At least 2 gemstones.
- **Key parameters:**
  - **Prong Size Ratio** — Prong size relative to average gemstone diameter. Default: `0.35`. Range: `0.1–0.5`.
  - **Prong Height Ratio** — Prong height relative to average gemstone diameter. Default: `0.3`. Range: `0.1–1.0`.
  - **Width Between Prongs Ratio** — Spacing between prong pair. Default: `0.65`. Range: `0.1–1.0`.
  - **Max Gap** — Maximum gap between gemstones for prong creation. Default: `0.5 mm`.
  - **Weld Distance** — Distance for merging nearby prongs. Default: `0.3 mm`.

---

![ChannelsBetweenGemstones icon](commands/ChannelsBetweenGemstones/resources/32x32@2x.png)
## ChannelsBetweenGemstones — Create channels between gemstones
- **Description:** Creates a network of channels connecting nearby gemstones based on distance constraint.
- **Selection:** At least 2 gemstones.
- **Key parameters:**
  - **Channel Ratio** — Channel width relative to gemstone size. Default: `0.5`. Range: `0.2–0.8`.
  - **Max Gap** — Maximum gap between gemstones for channel creation. Default: `0.5 mm`.

---

![CuttersForGemstones icon](commands/CuttersForGemstones/resources/32x32@2x.png)
## CuttersForGemstones — Create cutter bodies for gemstone seating
- **Description:** Generates cutter bodies around gemstone bodies created or recognized by the add-in.
- **Selection:** One or more gemstone bodies (the command filters for bodies marked as gemstones).
- **Key parameters:**
  - **Bottom Type** — Type of the bottom surface of the cutter. Defaults to `Hole`. Options: `Hole` (flat-bottom), `Cone` (tapered), `Hemisphere`.
  - **Height** — Cutter height extending above the gemstone girdle. Default: `0.4 mm`. Minimum: `0.1 mm`.
  - **Depth** — Depth of the cutter hole below the gemstone girdle. Default: `1.5 mm`. Minimum: `0 mm`.
  - **Size Ratio** — Scale factor relative to the gemstone diameter. Default: `1.0`. Range: `0.7–1.3`.
  - **Hole Ratio** — Central hole diameter as a fraction of cutter diameter. Default: `0.5`. Range: `0.2–0.8`.
  - **Cone Angle** — Cutter cone angle. Default: `41°`. Range: `30°–60°`.
- **Limitations and recommendations:**
  - When you edit an existing CuttersForGemstones operation, the add-in currently creates a new body instead of modifying the original. This behavior preserves the ability to change parameters (height, depth, scale, etc.) after the initial creation.
  - Do not manually edit cutter bodies with other modeling tools. If you modify a generated body and later change CuttersForGemstones parameters, the resulting geometry and dependency links can become unpredictable.
  - To update cutters, change parameters using the CuttersForGemstones command (so the operation regenerates correctly), then use Boolean operations to subtract the cutters from target bodies.

---

![SurfaceUnfold icon](commands/SurfaceUnfold/resources/32x32@2x.png)
## SurfaceUnfold — Unfold curved surfaces to flat 2D sketches (Early Preview)
- **Description:** Unfolds curved BRep faces or mesh bodies to flat 2D sketch patterns. Useful for creating manufacturing templates, patterns for flat materials, or analyzing surface distortion.
- **Selection:** 1 BRep face or 1 mesh body, plus 3 vertices for orientation (origin, X-direction, Y-direction).
- **Key parameters:**
  - **Select Source** — Select the face or mesh body to unfold.
  - **Origin Point** — Select a vertex or sketch point on the face to be the origin (0,0) of the sketch.
  - **X Direction Point** — Select a vertex or sketch point on the face to define the +X direction from origin.
  - **Y Direction Point** — Select a vertex or sketch point on the face to define the rotation (orientation) of the unfolded sketch.
  - **Construction Plane** — Select the construction plane where the unfolded sketch will be created. Default: XY plane.
  - **X Offset** — Offset along the X axis of the construction plane. Default: `0 mm`.
  - **Y Offset** — Offset along the Y axis of the construction plane. Default: `0 mm`.
  - **Accuracy** — Unfolding accuracy (0.5 - 10 mm). Minimum allowed is 0.5 mm to avoid excessive computation. Default: `0.5 mm`.
  - **Algorithm** — Select the unfolding algorithm: NURBS (parametric grid) or Mesh (tessellation). Default: `Mesh`.
- **Limitations:** This feature is in early preview and may have limitations with highly complex or distorted surfaces.

---

![ObjectsRefold icon](commands/ObjectsRefold/resources/32x32@2x.png)
## ObjectsRefold — Refold flat patterns onto curved surfaces (Early Preview)
- **Description:** Takes any BRep bodies and wraps them onto a curved surface created by SurfaceUnfold. This is the inverse operation of SurfaceUnfold.
- **Selection:** 1 sketch (created by SurfaceUnfold) and one or more BRep bodies to refold onto the original curved surface.
- **Key parameters:** None — the command uses metadata from the SurfaceUnfold sketch to reverse the unfolding transformation.
- **Limitations:** Currently, the command creates copies of the selected bodies instead of moving the existing ones. 

---

![Gemstones Info icon](commands/GemstonesInfo/resources/32x32@2x.png)
## GemstonesInfo — Show detected gemstone diameters on-model (Early Preview)
- **Description:** Detects gemstone bodies created by the add-in and overlays their diameters as on-model text labels to help with quick inspection and verification. The command dialog also displays a summary list of all gemstone sizes with their total counts, sorted from smallest to largest.
- **Selection:** No explicit selection required — the command scans the model for bodies marked as gemstones (including occurrences) and displays overlay text for each detected gemstone.
- **Behavior:** Uses attribute metadata attached to gemstone bodies to detect them, computes centroid and normal, and places text slightly offset along the gemstone normal (diameter shown in mm). The text is displayed using billboarding for better visibility from all angles. The summary list in the dialog shows each unique diameter with the number of gemstones of that size.
- **Limitations:** This feature is in early preview and may have limitations or unexpected behavior; user feedback is appreciated.