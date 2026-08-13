# L2 Team-Generated Task SOP

<!-- TEAM GENERATED — SAFE TO REGENERATE -->

## Planner Quick Facts

- CURRENT LEVEL: `L2`
- MATERIAL: Green-rimmed storage bin
- SOURCE: `input_6` (Pick Station 1)
- TARGET: `output_4` (Place Station 3)
- QUANTITY: `1`
- EXACT OBJECTS: `green_tote_b01_upper`, `green_tote_b01_lower`
- REQUIRED PLAN: `move input_6 → pick_up → move output_4 → place_down`
- The current task prompt and runtime mapping override stale examples in the generic Word SOP body.

- Source DOCX: `JCIIOT 2026 case 3 SOP.docx`
- Generator: `src/robot_agent/skills/read_document.py`
- Destination: team-owned SOP archive; locked competition knowledge is not modified

## Authority Rules

1. The Current Task Prompt below defines the requested material, human station names, and quantity.
2. Runtime environment, station IDs, and object names come from locked `knowledge/task_config.json`.
3. Station geometry comes only from the matching generated semantic map (with scene JSON fallback).
4. Ignore stale task names or station examples that appear later in the generic Word SOP body.
5. Never invent a coordinate, station ID, or object name when a source does not provide it.

## Current Task Prompt (authoritative)

> Current Task Material Information:
> Material Name: Green-rimmed storage bin
> Starting Location: Pick Station 1
> Target Location: Place Station 3
> Quantity to Transport: 1

## Parsed Task Summary

- Level: `L2`
- Case number: `3`
- Material: Green-rimmed storage bin
- Human source label: Pick Station 1
- Human target label: Place Station 3
- Quantity: `1`

## Runtime Mapping

- Scene prefix: `factory_sorting_3_3fo3errph7x9`
- Environment: `FactorySorting3_3FO3ERRPH7X9`
- Source station ID: `input_6`
- Target station ID: `output_4`
- Maximum score: `15`
- Exact object names, in configured order:
  - `green_tote_b01_upper`
  - `green_tote_b01_lower`

## Station Geometry

- Scene map: `factory_sorting_3_3fo3errph7x9_scene_regenerated_semantic_map.json`
- Coordinate frame: `mujoco_world_xy`
- Source center: `(11.937, 3.932)`
- Source navigation approach: `(13, 3.932)`
- Target center: `(-0.166, -7.29)`
- Target navigation approach: `(-1.02, -7.29)`

## BC Grasp Start Pose

- No fixed BC XY coordinate is copied into this SOP.
- The exact object pose must be read from the live MuJoCo scene at execution time.
- If an object-specific grasp start pose is required, the manipulation skill must derive and validate it from live state.
- Failure to resolve a live pose is an execution error; never substitute a remembered coordinate.

## Required Skill Flow

1. `move(target="input_6")`
2. `pick_up(object_name="green_tote_b01_upper")`
3. `move(target="output_4")` while carrying the object
4. `place_down(target="output_4")`

## Execution Checks

- Stop diagnosis at the first failed stage.
- A successful move proves navigation reached its target; it does not prove the BC grasp pose is correct.
- Do not treat a later place failure as independent when pick_up already failed.
- If pick_up fails, verify exact base pose, yaw, object_name, online observations, and checkpoint contract before retraining.

## Document Image Analysis

- Embedded image count: `5`
- VLM descriptions are advisory visual context; they are never a coordinate authority.
- `image2.png`:
  This image depicts a **modern manufacturing workstation** (likely for electronics assembly, kitting, or quality control) set within a larger factory floor. Here is a detailed breakdown of the layout: ## **Foreground Workstation (Primary Focus)** **Workbench/Table:** - **Surface:** Light blue work surface supported by a gray metal frame - **Structure:** Features an upper shelving unit with an overhead white canopy (possibly integrated lighting) **Objects on the Work Surface (Left to Right):** 1. **Left Green Bin:** A large, rectangular dark green bulk storage crate/bin positioned on the far left of the bench 2. **Center Processing Tray:** A white rectangular shallow container/tote positioned centrally between the green bins - Contains a bright **green insert/mat** (possibly an ESD-safe work surface or material holding area) - Has **yellow handles** on both the left and right sides for carrying 3. **Right Green Bin:** Identical to the left one, positioned symmetrically on the far right **Upper Storage Shelf (Above the Bench):** - Holds **15 small angled parts bins** arranged in a neat horizontal row - **Color Pattern (repeating 5 times):** Light Blue (Cyan) → Yellow/Gold → Purple - These appear to be component organizers for screws, electronic parts, or small hardware - **Backing:** A blue perforated pegboard panel sits behind the bins for tool/part hanging capability ## **Background Factory Environment** Visible through the open space
- `image1.png`:
  This image depicts a **modern, organized manufacturing workstation** (likely for electronics assembly or light industrial production) rendered in a clean, 3D CAD style. Here is a detailed breakdown of the layout: ## **Primary Workstation (Foreground)** **Position:** Center-front, dominating the immediate view - **Work Surface:** A large, light-blue ESD-safe style tabletop with rounded edges - **Active Tray:** Centered on the table is a white rectangular plastic bin/tray containing a **bright green** work mat or insert, with **yellow ergonomic handles** on the left and right sides - **Overhead Storage Rack:** - Mounted above the table on two vertical gray support posts - Holds **12 small angled bins** arranged in four repeating groups of three colors: **Teal → Yellow → Purple** (left to right) - These appear to be component organizers for screws, fasteners, or small parts - **Back Panel:** A **blue perforated pegboard** (with regular grid of holes) serving as the backdrop, featuring a blank **white rectangular area** in the upper-center (likely for posting work instructions, SOPs, or labels) ## **Mid-Ground Production Area** **Position:** Behind the primary station, showing depth of factory floor - **Secondary Workstations:** Multiple identical light-blue tables receding into the background - **Computer Terminal:** Visible monitor with a bright cyan/blue screen displaying data (positioned center-left in mid-ground) - **Conveyor System:** Dark-colored (black/dark gray) belt conveyor running horizontally through the middle ground, suggesting an assembly line flow - **Safety In
- `image5.png`:
  Based on the image provided, here is a detailed description of the factory layout and its components: ## **Primary Object (Foreground)** - **Green Plastic Container/Tote Bin**: A large, rectangular green industrial plastic container (likely an ESD-safe tote or logistics box) positioned centrally in the immediate foreground. It features reinforced rim edges and sits open-topped. ## **Workstation/Cart Structure** - **Metal Frame Assembly**: A silver-gray tubular metal framework surrounding the green container, appearing to be either: - A mobile workstation cart - An ESD (Electrostatic Discharge) safe workbench frame - A material handling rack **Frame Components:** - **Vertical support posts**: Four corner uprights extending above and below the container - **Horizontal rails**: Crossbars at multiple levels creating a protective cage around the container - **Blue Work Surface**: A cyan/blue flat platform forming the base where the green container rests - **Electrical Outlets**: Three white 3-prong power sockets mounted on the lower front horizontal rail of the frame (positioned below the green bin) ## **Background Production Equipment** Behind the main workstation, the image shows an industrial production line receding into the distance: - **Processing Machinery**: Large white and light-gray industrial units with: - Rectangular housings/enclosures - Open compartments or feed trays (black interior surfaces visible) - Horizontal processing surfaces or conveyor beds - **Structural Elements**: - **Blue vertical panels/columns**: Safety guarding or support structures (bright cyan/bl
- `image4.png`:
  This image depicts a **factory workstation or assembly cell** with the following key elements arranged from foreground to background: ## Foreground Workstation - **Work Table**: A prominent turquoise/cyan-colored work surface at the bottom of the frame, supported by a metal frame structure - **Overhead Gantry**: A white/light gray metal framework arching over the table with: - Two horizontal crossbars/rails - Four vertical support posts - **Power Strip/Outlets**: Mounted on the lower front rail—**10 electrical socket outlets** arranged in two clusters of 5 each (left group and right group), suggesting this is a powered workstation for tools, testing equipment, or soldering stations ## Mid-ground Machinery - **Conveyor System**: Black horizontal surfaces that appear to be conveyor belts or material transport mechanisms positioned behind the workstation - **Processing Equipment**: White/gray industrial machinery with stacked horizontal surfaces or trays, possibly for material handling, inspection, or assembly operations - **Structural Frame**: Additional metal framing supporting the conveyor system ## Background Elements - **Blue Vertical Structure**: A bright blue rectangular column or machine component visible in the rear center-left - **White Enclosure**: A large white cabinet or machine housing on the right side - **Additional Conveyors**: More black conveyor sections extending into the depth of the facility - **Flooring**: Light blue/cyan flooring consistent with cleanroom or high-tech manufacturing environments ## Overall Layout Interpretation This appears to be a **man
- `image3.png`:
  This is a **top-down isometric view of a smart factory floor layout** featuring automated production lines, material handling stations, and AGV (Automated Guided Vehicle) infrastructure. Here's a detailed breakdown: ## **Overall Layout Structure** The facility features **gray industrial flooring** with equipment arranged in roughly parallel rows running from front-to-back (bottom-to-top in the image). The left side contains AGV infrastructure, while the center and right contain manufacturing workstations. --- ## **1. Charging Stations (Left Side - AGV Infrastructure)** Four charging docks arranged vertically along the left edge: - **充电位1 (Charging Station 1)**: Bottom-left corner - **充电位2 (Charging Station 2)**: Above Station 1 - **充电位3 (Charging Station 3)**: Above Station 2 - **充电位4 (Charging Station 4)**: Top of the charging column *These appear to be robot/AGV charging docks with small device icons.* --- ## **2. Production Lines & Workstations (Center-Right)** ### **Primary Production Line (Left-Center)** A long **conveyor-based assembly line** with multiple processing units connected by belts, featuring: - Blue-accented machinery modules - Integrated conveyor transport system - Multiple input/output interfaces ### **Individual Workstations (Center to Right)** **Four standalone machine stations** arranged in a horizontal row
