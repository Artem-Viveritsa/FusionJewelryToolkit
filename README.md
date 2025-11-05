# Fusion 360 Jewelry Toolkit

A small collection of utilities that speed up jewelry modeling in Fusion 360. The add-in installs three commands in the Solid → Create menu.

Note: This add-in uses the Custom Feature Fusion API, which is currently in preview. Future Fusion 360 updates may require changes to the add-in.

## Installation

1. In Fusion 360, go to Utilities → Add-ins → Scripts and Add-ins.
2. Click the `+` button and choose "Script or Add-in from my computer".
3. Select the `FusionJewelryToolkit` folder and click Open.
4. To make the add-in run automatically when Fusion starts, enable the "Run on Startup" checkbox.
5. After installation, the commands appear under Solid → Create.

---

![Gemstones icon](commands/GemstonesOnFaceAtPoints/resources/32x32@2x.png)

## GemstonesOnFaceAtPoints — Place round gemstones on a face at specified points

- **Description:** Creates round-cut gemstone bodies at selected sketch points on a chosen face.
- **Selection:** 1 face and one or more sketch points. The face may have any curvature or complexity; the points do not need to lie directly on the face.
- **Key parameters:**
  - **Size** — Gemstone diameter. Default: `1.5 mm`. Minimum: `0.5 mm`.
  - **Flip (orientation)** — Flip the stone orientation. Default: false.
  - **Depth Offset (along face normal)** — Offset along the face normal. Default: `0 mm`.

---

![Prongs icon](commands/ProngsOnFaceAtPoints/resources/32x32@2x.png)

## ProngsOnFaceAtPoints — Generate prongs on a face at specified points

- **Description:** Generates prong bodies at selected sketch points on a chosen face.
- **Selection:** 1 face and one or more sketch points. The face may have any curvature or complexity; the points do not need to lie directly on the face.
- **Key parameters:**
  - **Size (prong base diameter)** — Default: `0.4 mm`. Minimum: `0.1 mm`.
  - **Height (prong height)** — Height above the face. Default: `0.4 mm`. Minimum: `0.1 mm`.

---

![Cutter icon](commands/Cutters/resources/32x32@2x.png)

## Cutters — Create cutter bodies for gemstone seating

- **Description:** Generates cutter bodies around gemstone bodies created or recognized by the add-in.
- **Selection:** One or more gemstone bodies (the command filters for bodies marked as gemstones).
- **Key parameters:**
  - **Height** — Cutter height extending above the gemstone girdle. Default: `0.4 mm`. Minimum: `0.1 mm`.
  - **Depth** — Depth of the cutter hole below the gemstone girdle. Default: `1.5 mm`. Minimum: `0 mm`.
  - **Size Ratio** — Scale factor relative to the gemstone diameter. Default: `1.0`. Range: `0.7–1.3`.
  - **Hole Ratio** — Central hole diameter as a fraction of cutter diameter. Default: `0.5`. Range: `0.2–0.8`.
  - **Cone Angle** — Cutter cone angle. Default: `41°`. Range: `30°–60°`.

### Limitations and recommendations

- When you edit an existing Cutters operation, the add-in currently creates a new body instead of modifying the original. This behavior preserves the ability to change parameters (height, depth, scale, etc.) after the initial creation.
- Do not manually edit cutter bodies with other modeling tools. If you modify a generated body and later change Cutters parameters, the resulting geometry and dependency links can become unpredictable.
- To update cutters, change parameters using the Cutters command (so the operation regenerates correctly), then use Boolean operations to subtract the cutters from target bodies.