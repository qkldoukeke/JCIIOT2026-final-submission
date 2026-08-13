# L4 Team-Generated Task SOP

<!-- TEAM GENERATED — SAFE TO REGENERATE -->

## Planner Quick Facts

- CURRENT LEVEL: `L4`
- MATERIAL: a blue, hollow plastic box
- SOURCE: `input_2` (Pick Station 5)
- TARGET: `output_5` (Place Station 2)
- QUANTITY: `1`
- EXACT OBJECTS: `blue_container_h01_back_upper`, `blue_container_h01_back_lower`
- REQUIRED PLAN: `move input_2 → pick_up → move output_5 → place_down`
- The current task prompt and runtime mapping override stale examples in the generic Word SOP body.

- Source DOCX: `JCIIOT 2026 case 7 SOP.docx`
- Generator: `src/robot_agent/skills/read_document.py`
- Destination: team-owned SOP archive; locked competition knowledge is not modified

## Authority Rules

1. The Current Task Prompt below defines the requested material, human station names, and quantity.
2. Runtime environment, station IDs, and object names come from locked `knowledge/task_config.json`.
3. Station geometry comes only from the matching generated semantic map (with scene JSON fallback).
4. Ignore stale task names or station examples that appear later in the generic Word SOP body.
5. Never invent a coordinate, station ID, or object name when a source does not provide it.

## Current Task Prompt (authoritative)

> Please strictly adhere to the Standard Operating Procedure (SOP) for this task. The object to be handled is a blue, hollow plastic box. The Pick Station is designated as Pick Station 5, and the Place Station is designated as Place Station 2.

## Parsed Task Summary

- Level: `L4`
- Case number: `7`
- Material: a blue, hollow plastic box
- Human source label: Pick Station 5
- Human target label: Place Station 2
- Quantity: `1`

## Runtime Mapping

- Scene prefix: `factory_sorting_7_3fo3erfky9rn`
- Environment: `FactorySorting7_3FO3ERFKY9RN`
- Source station ID: `input_2`
- Target station ID: `output_5`
- Maximum score: `25`
- Exact object names, in configured order:
  - `blue_container_h01_back_upper`
  - `blue_container_h01_back_lower`

## Station Geometry

- Scene map: `factory_sorting_7_3fo3erfky9rn_scene_regenerated_semantic_map.json`
- Coordinate frame: `mujoco_world_xy`
- Source center: `(-9.761, 5.01)`
- Source navigation approach: `(-8.3, 5.01)`
- Target center: `(4.872, -7.261)`
- Target navigation approach: `(4.02, -7.261)`

## BC Grasp Start Pose

- No fixed BC XY coordinate is copied into this SOP.
- The exact object pose must be read from the live MuJoCo scene at execution time.
- If an object-specific grasp start pose is required, the manipulation skill must derive and validate it from live state.
- Failure to resolve a live pose is an execution error; never substitute a remembered coordinate.

## Required Skill Flow

1. `move(target="input_2")`
2. `pick_up(object_name="blue_container_h01_back_upper")`
3. `move(target="output_5")` while carrying the object
4. `place_down(target="output_5")`

## Execution Checks

- Stop diagnosis at the first failed stage.
- A successful move proves navigation reached its target; it does not prove the BC grasp pose is correct.
- Do not treat a later place failure as independent when pick_up already failed.
- If pick_up fails, verify exact base pose, yaw, object_name, online observations, and checkpoint contract before retraining.

## Document Image Analysis

- Embedded image count: `5`
- No successful VLM image descriptions were available during generation.
