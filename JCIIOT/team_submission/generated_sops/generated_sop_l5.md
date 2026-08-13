# L5 Team-Generated Task SOP

<!-- TEAM GENERATED — SAFE TO REGENERATE -->

## Planner Quick Facts

- CURRENT LEVEL: `L5`
- MATERIAL: white-rimmed storage bins
- SOURCE: `input_1` (Pick Station 6)
- TARGET: `aux_output_1` (Place Station 1)
- QUANTITY: `3`
- EXACT OBJECTS: `white_tote_b01_left_center`, `white_tote_b01_left_front`, `white_tote_b01_left_back`
- REQUIRED PLAN: `move input_1 → pick_up → move aux_output_1 → place_down`
- The current task prompt and runtime mapping override stale examples in the generic Word SOP body.

- Source DOCX: `JCIIOT 2026 case 9 SOP.docx`
- Generator: `src/robot_agent/skills/read_document.py`
- Destination: team-owned SOP archive; locked competition knowledge is not modified

## Authority Rules

1. The Current Task Prompt below defines the requested material, human station names, and quantity.
2. Runtime environment, station IDs, and object names come from locked `knowledge/task_config.json`.
3. Station geometry comes only from the matching generated semantic map (with scene JSON fallback).
4. Ignore stale task names or station examples that appear later in the generic Word SOP body.
5. Never invent a coordinate, station ID, or object name when a source does not provide it.

## Current Task Prompt (authoritative)

> Move the three white-rimmed storage bins from Pick Station 6 to Place Station 1.

## Parsed Task Summary

- Level: `L5`
- Case number: `9`
- Material: white-rimmed storage bins
- Human source label: Pick Station 6
- Human target label: Place Station 1
- Quantity: `3`

## Runtime Mapping

- Scene prefix: `factory_sorting_9_3fo3ert2c5fp`
- Environment: `FactorySorting9_3FO3ERT2C5FP`
- Source station ID: `input_1`
- Target station ID: `aux_output_1`
- Maximum score: `30`
- Exact object names, in configured order:
  - `white_tote_b01_left_center`
  - `white_tote_b01_left_front`
  - `white_tote_b01_left_back`

## Station Geometry

- Scene map: `factory_sorting_9_3fo3ert2c5fp_scene_regenerated_semantic_map.json`
- Coordinate frame: `mujoco_world_xy`
- Source center: `(-14.544, 5.01)`
- Source navigation approach: `(-13.1, 5.01)`
- Target center: `(0.144, 8.473)`
- Target navigation approach: `(0.11, 7.55)`

## BC Grasp Start Pose

- No fixed BC XY coordinate is copied into this SOP.
- The exact object pose must be read from the live MuJoCo scene at execution time.
- If an object-specific grasp start pose is required, the manipulation skill must derive and validate it from live state.
- Failure to resolve a live pose is an execution error; never substitute a remembered coordinate.

## Required Skill Flow

1. `move(target="input_1")`
2. Pick the required objects in configured order: `white_tote_b01_left_center`, `white_tote_b01_left_front`, `white_tote_b01_left_back`
3. `move(target="aux_output_1")` while carrying the object
4. `place_down(target="aux_output_1")`
5. Repeat the pick/transport/place cycle until `3` objects are placed.

## Execution Checks

- Stop diagnosis at the first failed stage.
- A successful move proves navigation reached its target; it does not prove the BC grasp pose is correct.
- Do not treat a later place failure as independent when pick_up already failed.
- If pick_up fails, verify exact base pose, yaw, object_name, online observations, and checkpoint contract before retraining.

## Document Image Analysis

- Embedded image count: `5`
- No successful VLM image descriptions were available during generation.
