# Fusion 360 Jewelry Toolkit

A small collection of utilities that speed up jewelry modeling in Fusion 360. The add-in installs six commands in the Solid → Create menu.

Note: This add-in uses the Custom Feature Fusion API, which is currently in preview. Future Fusion 360 updates may require changes to the add-in.

## Installation
1. In Fusion 360, go to Utilities → Add-ins → Scripts and Add-ins.
2. Click the `+` button and choose "Script or Add-in from my computer".
3. Select the `FusionJewelryToolkit` folder and click Open.
4. To make the add-in run automatically when Fusion starts, enable the "Run on Startup" checkbox.
5. After installation, the commands appear under Solid → Create.

## What's new in v0.5.0
- Added option for `CuttersForGemstones` to configure the cutter bottom type (Hole, Cone, Hemisphere).

---

![Gemstones icon](commands/GemstonesOnFaceAtPoints/resources/32x32@2x.png)
## GemstonesOnFaceAtPoints — Place round gemstones on a face at specified points
- **Description:** Creates round-cut gemstone bodies at selected sketch points on a chosen face.
- **Selection:** 1 face and one or more sketch points. The face may have any curvature or complexity; the points do not need to lie directly on the face.
- **Key parameters:**
  - **Size** — Gemstone diameter. Default: `1.5 mm`. Determines the overall size of the gemstone.
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: false.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

![Gemstones icon](commands/GemstonesOnFaceAtCircles/resources/32x32@2x.png)
## GemstonesOnFaceAtCircles — Place round gemstones on a face at sketch circles
- **Description:** Creates round-cut gemstone bodies at selected sketch circles on a chosen face. The gemstone size matches the circle diameter.
- **Selection:** 1 face and one or more sketch circles. The face may have any curvature or complexity; the circles do not need to lie directly on the face. Minimum circle diameter is `0.5 mm`.
- **Key parameters:**
  - **Flip (orientation)** — Flip the stone orientation. Reverses the direction the gemstone faces relative to the surface. Default: false.
  - **Absolute Depth Offset** — Additional depth offset in absolute units. Adds a fixed depth to the gemstone beyond the relative offset. Default: `0 mm`.
  - **Relative Depth Offset** — Depth offset as a fraction of gemstone size. Controls how deep the gemstone sits (0.1 = 10% of diameter). Default: `0`.

---

![Prongs icon](commands/ProngsOnFaceAtPoints/resources/32x32@2x.png)
## ProngsOnFaceAtPoints — Generate prongs on a face at specified points
- **Description:** Generates prong bodies at selected sketch points on a chosen face.
- **Selection:** 1 face and one or more sketch points. The face may have any curvature or complexity; the points do not need to lie directly on the face.
- **Key parameters:**
  - **Size (prong base diameter)** — Default: `0.4 mm`. Minimum: `0.1 mm`.
  - **Height (prong height)** — Height above the face. Default: `0.4 mm`. Minimum: `0.1 mm`.

---

![ProngsBetweenGemstones icon](commands/ProngsBetweenGemstones/resources/32x32@2x.png)
## ProngsBetweenGemstones — Create prongs between gemstones
- **Description:** Creates prongs at the midpoint between nearby gemstones based on distance constraint.
- **Selection:** At least 2 gemstones.
- **Key parameters:**
  - **Prong Size Ratio** — Prong size relative to average gemstone diameter. Default: `0.3`. Range: `0.1–0.5`.
  - **Prong Height Ratio** — Prong height relative to average gemstone diameter. Default: `0.3`. Range: `0.1–1.0`.
  - **Width Between Prongs Ratio** — Spacing between prong pair. Default: `0.5`. Range: `0.1–1.0`.
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