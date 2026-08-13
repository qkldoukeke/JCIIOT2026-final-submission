# L3 Team-Generated Task SOP

<!-- TEAM GENERATED — SAFE TO REGENERATE -->

## Planner Quick Facts

- CURRENT LEVEL: `L3`
- MATERIAL: a blue material transfer bin
- SOURCE: `aux_input_1` (Pick Station 1)
- TARGET: `output_5` (Place Station 2)
- QUANTITY: `1`
- EXACT OBJECTS: `blue_tote_b01_far_right`, `blue_tote_b01_near_right`
- REQUIRED PLAN: `move aux_input_1 → pick_up → move output_5 → place_down`
- The current task prompt and runtime mapping override stale examples in the generic Word SOP body.

- Source DOCX: `JCIIOT 2026 case 5 SOP.docx`
- Generator: `src/robot_agent/skills/read_document.py`
- Destination: team-owned SOP archive; locked competition knowledge is not modified

## Authority Rules

1. The Current Task Prompt below defines the requested material, human station names, and quantity.
2. Runtime environment, station IDs, and object names come from locked `knowledge/task_config.json`.
3. Station geometry comes only from the matching generated semantic map (with scene JSON fallback).
4. Ignore stale task names or station examples that appear later in the generic Word SOP body.
5. Never invent a coordinate, station ID, or object name when a source does not provide it.

## Current Task Prompt (authoritative)

> Please follow the SOP. The object is a blue material transfer bin. The Pick Station is Pick Station 1, and the Place Station is Place Station 2.

## Parsed Task Summary

- Level: `L3`
- Case number: `5`
- Material: a blue material transfer bin
- Human source label: Pick Station 1
- Human target label: Place Station 2
- Quantity: `1`

## Runtime Mapping

- Scene prefix: `factory_sorting_5_3fo3ertpxeut`
- Environment: `FactorySorting5_3FO3ERTPXEUT`
- Source station ID: `aux_input_1`
- Target station ID: `output_5`
- Maximum score: `20`
- Exact object names, in configured order:
  - `blue_tote_b01_far_right`
  - `blue_tote_b01_near_right`

## Station Geometry

- Scene map: `factory_sorting_5_3fo3ertpxeut_scene_regenerated_semantic_map.json`
- Coordinate frame: `mujoco_world_xy`
- Source center: `(0.144, 8.473)`
- Source navigation approach: `(0.11, 7.55)`
- Target center: `(4.872, -7.261)`
- Target navigation approach: `(4.02, -7.261)`

## BC Grasp Start Pose

- No fixed BC XY coordinate is copied into this SOP.
- The exact object pose must be read from the live MuJoCo scene at execution time.
- If an object-specific grasp start pose is required, the manipulation skill must derive and validate it from live state.
- Failure to resolve a live pose is an execution error; never substitute a remembered coordinate.

## Required Skill Flow

1. `move(target="aux_input_1")`
2. `pick_up(object_name="blue_tote_b01_far_right")`
3. `move(target="output_5")` while carrying the object
4. `place_down(target="output_5")`

## Execution Checks

- Stop diagnosis at the first failed stage.
- A successful move proves navigation reached its target; it does not prove the BC grasp pose is correct.
- Do not treat a later place failure as independent when pick_up already failed.
- If pick_up fails, verify exact base pose, yaw, object_name, online observations, and checkpoint contract before retraining.

## Document Image Analysis

- Embedded image count: `5`
- VLM descriptions are advisory visual context; they are never a coordinate authority.
- `image2.png`:
  This image depicts a simplified **factory or warehouse workstation** with the following elements: ## Main Objects & Positions **1. Work Table / Workbench** - **Color:** Teal/turquoise (bright cyan-green) - **Shape:** Rectangular flat surface - **Position:** Centered in the lower portion of the image - **Support:** Supported by at least two visible gray/silver cylindrical legs (one on the far left, one on the far right) **2. Blue Plastic Crates/Containers (2 units)** - **Color:** Royal blue (solid, opaque) - **Shape:** Rectangular industrial storage boxes with reinforced edges/rims - **Position:** - **Left crate:** Positioned on the left side of the table surface, roughly centered horizontally on the left half - **Right crate:** Positioned on the right side of the table surface, mirrored to the left crate - **Spacing:** Separated by a gap of empty teal table space between them (roughly equal to the width of one crate) - **Orientation:** Both facing forward, showing their front panels ## Environment & Background - **Back wall:** Plain light gray or off-white vertical surface - **Floor:** Light grayish-green horizontal surface visible beneath the table - **Lighting:** Even, diffuse lighting with soft shadows cast behind the crates onto the back wall - **Overall aesthetic:** Clean, minimalistic 3D render style (likely a digital simulation or CAD visualization) ## Layout Summary This appears to be a **material staging area** or **packing station** where two containers are positioned side-by-side on a work surface, possibly for assembly line feeding, quality inspection, or order 
- `image1.png`:
  Looking at this image, I see a **minimalist factory workspace** with the following elements: ## Main Object: Work Table - **Large cyan/turquoise rectangular table surface** positioned horizontally across the center-lower portion of the image - The tabletop is flat, elongated, and spans most of the width of the image ## Support Structures - **Two cylindrical legs/pillars** (gray/silver) supporting the table: - **Left leg**: Positioned under the left portion of the table - **Right leg**: Positioned under the right portion of the table - Both appear to be round columns extending from the floor to the underside of the tabletop ## Background/Environment - **Upper background**: Plain white or off-white wall/ceiling area - **Lower background**: Light green floor surface beneath the table - **Vertical line**: A thin, faint line visible near the center-right (possibly a cable, wire, or seam) ## Notable Absences This appears to be a **very simplified or schematic representation** - there are no visible: - Workers or operators - Machinery or equipment on the table - Additional workstations or assembly lines - Tools, materials, or products - Complex infrastructure **Overall impression**: This looks like a basic **workbench or inspection table** setup in a clean, minimal industrial environment, possibly representing a single station in a larger production line, or a placeholder/template image for a factory layout diagram. Is this part of a larger layout system, or would you like me to describe potential configurations for how this table might fit into a complete production workflow?
- `image5.png`:
  This image depicts a **3D-rendered industrial factory cell or production line** with a clean, modern aesthetic typical of lean manufacturing or electronics assembly environments. Here is a detailed breakdown of the layout: ## **Foreground Elements** - **Primary Workstation/Table**: Dominating the foreground is a large, rectangular workbench with a **bright cyan/turquoise work surface** and a white structural frame (legs and support beams). It appears to be an inspection, assembly, or packing station. ## **Mid-Ground & Production Equipment** - **Left Station (Processing Unit)**: A substantial piece of industrial machinery featuring: - White housing/enclosure - A prominent **vertical bright blue component** (likely a safety guard, hopper, or processing module) - A dark horizontal **conveyor or transfer arm** extending from its right side toward the center - **Central/Background Workstations**: A series of **2-3 gray/white modular machines** or workstations arranged in a line receding into the background: - These appear to be automated stations, test equipment, or secondary assembly units - Some have flat tops (possibly with cyan surfaces matching the foreground table) - They are positioned at varying depths, creating a production flow from back-to-front or left-to-right ## **Status & Safety Objects** - **Andon Signal Towers (2)**: Mounted on the right-side equipment: - **Rear tower**: Positioned on the furthest visible machine, displaying stacked **red-green-black** light segments - **Front tower**: Located on the mid-right station, also with **red-green-black** configuration
- `image4.png`:
  This image depicts a **factory workstation or automated inspection cell** with the following elements: ## Primary Objects & Positions **Central Work Area:** - **Blue plastic container/bin** – Positioned centrally on the work surface; appears to be a material handling tote or work-in-progress (WIP) container - **Cyan/turquoise work surface** – A flat tabletop or conveyor belt forming the main working plane; the blue container rests directly on it - **White structural frame** – Supports the cyan surface; consists of vertical legs and horizontal beams forming a table-like structure **Status Indicators (Right Side):** - **Two Andon tower lights** – Mounted on the right side of the station: - *Inner light*: Positioned mid-right, showing stacked red (top), green (middle), and black (base) segments - *Outer light*: Positioned further right with identical red-green-black color configuration - These typically indicate machine status (running/idle/error) **Background Elements:** - **Cyan vertical structure** – Visible behind and to the left of the blue container; possibly part of a machine enclosure, safety guard, or adjacent conveyor system - **White wall/paneling** – Forms the backdrop; clean industrial aesthetic suggesting a controlled manufacturing environment **Lower Structure:** - **Green panel sections** – Visible at bottom left and bottom right beneath the main table; likely base cabinets, safety guarding, or equipment housings - **Dark gray/black structural elements** – Horizontal beams or machine bases below the white frame - **Yellow accent line** – Thin horizontal yellow 
- `image3.png`:
  This is a **3D isometric view of an automated factory floor** featuring six parallel production lines arranged in a row, with various material handling stations and auxiliary equipment. Here's a detailed breakdown: ## **Production Lines (6 Main Lines)** Arranged horizontally from **left to right**, each consisting of white industrial machinery with conveyor systems: - **Line 1** (far left): Longest assembly line with blue accent components - **Line 2**: Mid-length processing unit - **Line 3** (center): Central processing station - **Lines 4-6** (right side): Three identical shorter workstations arranged in a cluster ## **Station Types & Positions** ### **🔋 Charging Stations (Left Edge)** Vertical column of 4 AGV/Robot charging docks: - **充电位1** (Charging Station 1) – Bottom left corner - **充电位2** – Above Station 1 - **充电位3** – Above Station 2 - **充电位4** – Top of the charging column ### **📥 Loading Stations (上料点) – Front/Side Positions** Input points where materials enter the system: - **上料点1 & 2** – Left side of Line 1 (front) - **上料点3** – Front of Line 2 - **上料点4** – Front of Line 3 (center) - **上料点5** – Front of Line 5 - **上料点6** – Front of Line 6 (far right) ### **📤 Unloading Stations (下料点) – Rear Positions** Output points where finished goods exit: - **
