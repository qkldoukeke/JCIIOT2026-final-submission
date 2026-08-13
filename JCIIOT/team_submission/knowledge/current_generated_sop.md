# L1 Team-Generated Task SOP

<!-- TEAM GENERATED — SAFE TO REGENERATE -->

## Planner Quick Facts

- CURRENT LEVEL: `L1`
- MATERIAL: blue, hollow plastic box
- SOURCE: `input_5` (Pick Station 2)
- TARGET: `output_4` (Place Station 3)
- QUANTITY: `1`
- EXACT OBJECTS: `line_5_container_h01_near`, `line_5_container_h01_far`
- REQUIRED PLAN: `move input_5 → pick_up → move output_4 → place_down`
- The current task prompt and runtime mapping override stale examples in the generic Word SOP body.

- Source DOCX: `JCIIOT 2026 case 1 SOP.docx`
- Generator: `src/robot_agent/skills/read_document.py`
- Destination: team-owned SOP archive; locked competition knowledge is not modified

## Authority Rules

1. The Current Task Prompt below defines the requested material, human station names, and quantity.
2. Runtime environment, station IDs, and object names come from locked `knowledge/task_config.json`.
3. Station geometry comes only from the matching generated semantic map (with scene JSON fallback).
4. Ignore stale task names or station examples that appear later in the generic Word SOP body.
5. Never invent a coordinate, station ID, or object name when a source does not provide it.

## Current Task Prompt (authoritative)

> Task Prompt: For this task, you need to transport a blue, hollow plastic box. Please move it from the starting point "Pick Station 2" to the destination "Place Station 3". Please follow the Standard Operating Procedure (SOP).

## Parsed Task Summary

- Level: `L1`
- Case number: `1`
- Material: blue, hollow plastic box
- Human source label: Pick Station 2
- Human target label: Place Station 3
- Quantity: `1`

## Runtime Mapping

- Scene prefix: `factory_sorting_1_3fo3erfhisem`
- Environment: `FactorySorting1_3FO3ERFHISEM`
- Source station ID: `input_5`
- Target station ID: `output_4`
- Maximum score: `10`
- Exact object names, in configured order:
  - `line_5_container_h01_near`
  - `line_5_container_h01_far`

## Station Geometry

- Scene map: `factory_sorting_1_3fo3erfhisem_scene_regenerated_semantic_map.json`
- Coordinate frame: `mujoco_world_xy`
- Source center: `(7.186, 3.938)`
- Source navigation approach: `(8, 4.619)`
- Target center: `(-0.166, -7.29)`
- Target navigation approach: `(-1.02, -7.29)`

## BC Grasp Start Pose

- No fixed BC XY coordinate is copied into this SOP.
- The exact object pose must be read from the live MuJoCo scene at execution time.
- If an object-specific grasp start pose is required, the manipulation skill must derive and validate it from live state.
- Failure to resolve a live pose is an execution error; never substitute a remembered coordinate.

## Required Skill Flow

1. `move(target="input_5")`
2. `pick_up(object_name="line_5_container_h01_near")`
3. `move(target="output_4")` while carrying the object
4. `place_down(target="output_4")`

## Execution Checks

- Stop diagnosis at the first failed stage.
- A successful move proves navigation reached its target; it does not prove the BC grasp pose is correct.
- Do not treat a later place failure as independent when pick_up already failed.
- If pick_up fails, verify exact base pose, yaw, object_name, online observations, and checkpoint contract before retraining.

## Document Image Analysis

- Embedded image count: `5`
- No successful VLM image descriptions were available during generation.
