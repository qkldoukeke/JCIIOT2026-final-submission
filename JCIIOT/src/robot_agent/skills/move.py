"""Move skill — navigate the robot base to a target via A* + backend."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
import re

import numpy as np

from robot_agent.core.types import ExecutionContext, SkillResult
from robot_agent.skills.base import BaseSkill
from robot_agent.skills.task_station_mapping import (
    configured_station_for_role,
    resolve_configured_station,
)

logger = logging.getLogger(__name__)


def _load_path_planning_parameters() -> dict[str, float]:
    """Read player-tunable path parameters from the allowed knowledge file."""
    params_path = (
        Path(__file__).resolve().parents[3]
        / "knowledge"
        / "robot_params.json"
    )
    data = json.loads(params_path.read_text(encoding="utf-8"))
    navigation = data.get("navigation", {})
    extra_clearance = float(navigation.get("path_extra_clearance", 0.0))
    endpoint_exemption = float(
        navigation.get("path_endpoint_exemption", extra_clearance)
    )
    source_egress_retreat = float(
        navigation.get("source_egress_retreat", 0.60)
    )
    source_egress_mode = (
        "outward_axis"
        if "source_egress_retreat" in navigation
        else "semantic_source_approach"
    )
    if not np.isfinite(extra_clearance) or extra_clearance < 0.0:
        raise ValueError(
            "navigation.path_extra_clearance must be a finite non-negative number"
        )
    if not np.isfinite(endpoint_exemption) or endpoint_exemption < extra_clearance:
        raise ValueError(
            "navigation.path_endpoint_exemption must be finite and no smaller "
            "than navigation.path_extra_clearance"
        )
    if (
        not np.isfinite(source_egress_retreat)
        or not 0.10 <= source_egress_retreat <= 1.50
    ):
        raise ValueError(
            "navigation.source_egress_retreat must be between 0.10 and 1.50 m"
        )
    return {
        "extra_clearance": extra_clearance,
        "endpoint_exemption": endpoint_exemption,
        "source_egress_retreat": source_egress_retreat,
        "source_egress_mode": source_egress_mode,
    }


def _inflate_transit_obstacles(
    grid: np.ndarray,
    *,
    resolution: float,
    extra_clearance: float,
    endpoint_exemption: float,
    bounds: dict,
    start_xy: np.ndarray,
    goal_xy: np.ndarray,
) -> np.ndarray:
    """Inflate obstacles while retaining data-defined endpoint access.

    The generated map already includes the circular mobile-base footprint.
    This additional layer covers arm / carried-object overhang during transit.
    Only originally passable cells may be reopened around the two endpoints,
    so this cannot cut a tunnel through station geometry.
    """
    if extra_clearance <= 0.0:
        return grid

    from robot_agent.core.navigation import world_to_grid

    passable = np.isin(grid, (0, 3, 4))
    blocked = ~passable
    inflated = blocked.copy()
    rows, cols = grid.shape
    radius_cells = int(math.ceil(extra_clearance / resolution))

    for drow in range(-radius_cells, radius_cells + 1):
        for dcol in range(-radius_cells, radius_cells + 1):
            if math.hypot(drow, dcol) * resolution > extra_clearance + 1e-9:
                continue
            dst_rows = slice(max(0, drow), min(rows, rows + drow))
            dst_cols = slice(max(0, dcol), min(cols, cols + dcol))
            src_rows = slice(max(0, -drow), min(rows, rows - drow))
            src_cols = slice(max(0, -dcol), min(cols, cols - dcol))
            inflated[dst_rows, dst_cols] |= blocked[src_rows, src_cols]

    safe_grid = grid.copy()
    safe_grid[inflated & passable] = 1

    exemption_cells = int(math.ceil(endpoint_exemption / resolution))
    for endpoint in (start_xy, goal_xy):
        center_row, center_col = world_to_grid(
            float(endpoint[0]),
            float(endpoint[1]),
            bounds,
            resolution,
        )
        for drow in range(-exemption_cells, exemption_cells + 1):
            for dcol in range(-exemption_cells, exemption_cells + 1):
                if (
                    math.hypot(drow, dcol) * resolution
                    > endpoint_exemption + 1e-9
                ):
                    continue
                row = center_row + drow
                col = center_col + dcol
                if 0 <= row < rows and 0 <= col < cols and passable[row, col]:
                    safe_grid[row, col] = grid[row, col]
    return safe_grid


class MoveSkill(BaseSkill):
    """Navigate the mobile base to a named station or world coordinate.

    Requires a backend, scene context, and occupancy grid — no mock fallback.
    """

    def __init__(
        self,
        *,
        backend,
        scene_context,
        grid: np.ndarray,
        path_spacing: float = 0.35,
    ) -> None:
        super().__init__(
            name="move",
            description="Move to a specified location",
            keywords=(
                "move", "go", "navigate",
                "move", "go", "navigate", "travel", "drive", "approach",
            ),
        )
        self._backend = backend
        self._scene = scene_context
        self._grid = grid
        self._path_spacing = path_spacing
        path_parameters = _load_path_planning_parameters()
        self._extra_clearance = path_parameters["extra_clearance"]
        self._endpoint_exemption = path_parameters["endpoint_exemption"]
        self._source_egress_retreat = path_parameters[
            "source_egress_retreat"
        ]
        self._source_egress_mode = path_parameters["source_egress_mode"]
        self._last_planned_clearance = 0.0

    # ── public API ──────────────────────────────────────────

    def run(self, context: ExecutionContext) -> SkillResult:
        requested_target: str = (
            context.metadata.get("inputs", {}).get("target")
            or context.task
        )
        target, station_mapping = resolve_configured_station(
            self._backend,
            requested_target,
        )

        goal_xy = self._resolve_target(target)
        if goal_xy is None:
            return SkillResult(
                skill_name=self.name,
                success=False,
                message=f"Cannot resolve target location: {target}",
                payload={
                    "action": "move",
                    "target": target,
                    "requested_target": requested_target,
                    "station_mapping": station_mapping,
                },
            )

        start_xy, start_yaw = self._backend.get_base_pose()
        path, source_egress = self._plan_execution_path(start_xy, goal_xy)
        if path is None:
            return SkillResult(
                skill_name=self.name,
                success=False,
                message=f"A* planning failed: {target}",
                payload={
                    "action": "move",
                    "target": target,
                    "requested_target": requested_target,
                    "station_mapping": station_mapping,
                    "source_egress": source_egress,
                    "start": start_xy.tolist(),
                },
            )

        reached = self._backend.follow_path(path)
        final_xy, final_yaw = self._backend.get_base_pose()
        path_length = float(
            sum(
                np.linalg.norm(current - previous)
                for previous, current in zip(path, path[1:])
            )
        )
        return SkillResult(
            skill_name=self.name,
            success=reached,
            message=f"Moved to: {target}" if reached else f"Failed to reach: {target}",
            payload={
                "action": "move",
                "target": target,
                "requested_target": requested_target,
                "station_mapping": station_mapping,
                "source_egress": source_egress,
                "goal_xy": goal_xy.tolist(),
                "start_base_pose": {
                    "xy": start_xy.tolist(),
                    "yaw": float(start_yaw),
                    "robot_base_pos": [float(start_xy[0]), float(start_xy[1]), 0.0],
                    "robot_base_ori": [0.0, 0.0, float(start_yaw)],
                },
                "final_base_pose": {
                    "xy": final_xy.tolist(),
                    "yaw": float(final_yaw),
                    "robot_base_pos": [float(final_xy[0]), float(final_xy[1]), 0.0],
                    "robot_base_ori": [0.0, 0.0, float(final_yaw)],
                },
                "waypoints": len(path),
                "path_length_m": path_length,
                "path_extra_clearance_m": self._last_planned_clearance,
                "max_linear_mps": float(
                    getattr(self._backend, "_max_linear", 0.0)
                ),
                "reached": reached,
            },
        )

    # ── internal ────────────────────────────────────────────

    def _plan_execution_path(
        self,
        start_xy: np.ndarray,
        goal_xy: np.ndarray,
    ) -> tuple[list[np.ndarray] | None, dict | None]:
        """Plan carried transit with a validated map-defined reverse egress.

        The precise grasp pose is closer to the station than its navigation
        approach. If A* chooses a diagonal first step there, the held object or
        extended arms can sweep through material still staged at the source.
        Move straight along the station's outward axis first, then begin A*.
        Starting from the live grasp pose instead of moving to the shared
        approach point preserves the object's lateral lane and avoids sweeping
        through a neighbouring item.
        """
        held_object = getattr(self._backend, "_held_crate_name", None)
        source = configured_station_for_role(self._backend, "source")
        if held_object and source:
            try:
                source_approach = np.asarray(
                    self._scene.approach_xy(source),
                    dtype=float,
                )
                if self._source_egress_mode == "semantic_source_approach":
                    egress_distance = float(
                        np.linalg.norm(source_approach - start_xy)
                    )
                    if 0.08 < egress_distance < 1.50:
                        transit = self._plan(source_approach, goal_xy)
                        if transit is not None:
                            path = [
                                np.asarray(start_xy, dtype=float).copy(),
                                source_approach.copy(),
                            ]
                            for waypoint in transit:
                                waypoint = np.asarray(waypoint, dtype=float)
                                if np.linalg.norm(waypoint - path[-1]) > 0.02:
                                    path.append(waypoint.copy())
                            return path, {
                                "source": source,
                                "held_object": str(held_object),
                                "start_xy": np.asarray(
                                    start_xy,
                                    dtype=float,
                                ).tolist(),
                                "egress_xy": source_approach.tolist(),
                                "egress_distance_m": egress_distance,
                                "method": "straight_to_semantic_source_approach",
                            }
                station_info = self._scene.input_ports.get(source)
                if station_info is None:
                    station_info = self._scene.output_ports.get(source)
                if station_info is None:
                    raise KeyError(f"Unknown source station: {source}")
                source_center = np.asarray(
                    station_info.center[:2],
                    dtype=float,
                )
                outward = source_approach - source_center
                outward_norm = float(np.linalg.norm(outward))
                if outward_norm <= 1e-6:
                    raise ValueError(
                        f"Source station {source} has no usable outward axis"
                    )
                outward_unit = outward / outward_norm
                egress_distance = self._source_egress_retreat
                egress_xy = (
                    np.asarray(start_xy, dtype=float)
                    + outward_unit * egress_distance
                )
                valid_egress_distance = 0.08 < egress_distance < 1.50
                egress_is_passable = (
                    valid_egress_distance
                    and self._segment_is_passable(start_xy, egress_xy)
                )
                if egress_is_passable:
                    transit = self._plan(egress_xy, goal_xy)
                    if transit is not None:
                        path = [
                            np.asarray(start_xy, dtype=float).copy(),
                            egress_xy.copy(),
                        ]
                        for waypoint in transit:
                            waypoint = np.asarray(waypoint, dtype=float)
                            if np.linalg.norm(waypoint - path[-1]) > 0.02:
                                path.append(waypoint.copy())
                        return path, {
                            "source": source,
                            "held_object": str(held_object),
                            "start_xy": np.asarray(
                                start_xy,
                                dtype=float,
                            ).tolist(),
                            "source_center_xy": source_center.tolist(),
                            "source_approach_xy": source_approach.tolist(),
                            "outward_unit_xy": outward_unit.tolist(),
                            "egress_xy": egress_xy.tolist(),
                            "egress_distance_m": egress_distance,
                            "method": (
                                "straight_reverse_along_semantic_source_axis"
                            ),
                        }
                    logger.warning(
                        "source-station egress cannot connect to target; "
                        "falling back to direct A*: %s",
                        source,
                    )
                    fallback = self._plan(start_xy, goal_xy)
                    return fallback, {
                        "source": source,
                        "held_object": str(held_object),
                        "start_xy": np.asarray(
                            start_xy,
                            dtype=float,
                        ).tolist(),
                        "source_center_xy": source_center.tolist(),
                        "source_approach_xy": source_approach.tolist(),
                        "outward_unit_xy": outward_unit.tolist(),
                        "rejected_egress_xy": egress_xy.tolist(),
                        "egress_distance_m": egress_distance,
                        "method": "a_star_fallback_egress_transit_failed",
                    }
                if valid_egress_distance:
                    logger.warning(
                        "source-station straight egress is blocked in the "
                        "current occupancy grid; falling back to A*: %s",
                        source,
                    )
                    fallback = self._plan(start_xy, goal_xy)
                    return fallback, {
                        "source": source,
                        "held_object": str(held_object),
                        "start_xy": np.asarray(
                            start_xy,
                            dtype=float,
                        ).tolist(),
                        "source_center_xy": source_center.tolist(),
                        "source_approach_xy": source_approach.tolist(),
                        "outward_unit_xy": outward_unit.tolist(),
                        "rejected_egress_xy": egress_xy.tolist(),
                        "egress_distance_m": egress_distance,
                        "method": "a_star_fallback_blocked_straight_egress",
                    }
            except Exception:
                logger.exception("source-station egress planning failed")

        return self._plan(start_xy, goal_xy), None

    def _segment_is_passable(
        self,
        start_xy: np.ndarray,
        end_xy: np.ndarray,
    ) -> bool:
        """Return whether a direct base segment stays in map-passable cells.

        Endpoint exemptions used by A* must not silently authorize a straight
        motion through station geometry. Sample the original generated grid so
        a narrow or side-exit workstation can fall back to its proven A* path.
        """
        from robot_agent.core.navigation import world_to_grid

        start = np.asarray(start_xy, dtype=float)
        end = np.asarray(end_xy, dtype=float)
        distance = float(np.linalg.norm(end - start))
        resolution = float(self._scene.resolution)
        sample_spacing = max(0.02, resolution * 0.5)
        sample_count = max(2, int(math.ceil(distance / sample_spacing)) + 1)
        rows, cols = self._grid.shape

        for fraction in np.linspace(0.0, 1.0, sample_count):
            point = start + (end - start) * float(fraction)
            row, col = world_to_grid(
                float(point[0]),
                float(point[1]),
                self._scene.bounds,
                resolution,
            )
            if not (0 <= row < rows and 0 <= col < cols):
                return False
            if int(self._grid[row, col]) not in (0, 3, 4):
                return False
        return True

    def _resolve_target(self, target: str) -> np.ndarray | None:
        """Convert a target description to a (2,) world xy position.

        Resolution order:
        1. Known station name via ``SceneContext.approach_xy()``
        2. Direct (x, y) tuple in the target string
        """
        # 1) named station. Resolve an exact canonical id first, then search
        # descriptions by longest id. This prevents ``aux_input_1`` from being
        # mistaken for its substring ``input_1``.
        target_text = str(target).strip()
        port_names = list(self._scene.all_port_names())
        if target_text in port_names:
            return self._scene.approach_xy(target_text)

        for name in sorted(port_names, key=len, reverse=True):
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
            if re.search(pattern, target_text):
                return self._scene.approach_xy(name)

        # 2) numeric "x, y"
        nums = re.findall(r"[-+]?\d*\.?\d+", target_text)
        if len(nums) >= 2:
            try:
                return np.array([float(nums[0]), float(nums[1])], dtype=float)
            except ValueError:
                pass

        return None

    def _plan(
        self, start_xy: np.ndarray, goal_xy: np.ndarray,
    ) -> list[np.ndarray] | None:
        """Run A* and return a world-frame path, or None on failure."""
        from robot_agent.core.map_loader import plan_world_path

        try:
            scene_dict = {
                "bounds": self._scene.bounds,
                "resolution": self._scene.resolution,
            }
            resolution = float(self._scene.resolution)
            clearance_candidates: list[float] = []
            clearance = self._extra_clearance
            while clearance > 1e-9:
                clearance_candidates.append(clearance)
                clearance = max(0.0, clearance - resolution)
            clearance_candidates.append(0.0)

            last_error: Exception | None = None
            for clearance in clearance_candidates:
                planning_grid = _inflate_transit_obstacles(
                    self._grid,
                    resolution=resolution,
                    extra_clearance=clearance,
                    endpoint_exemption=self._endpoint_exemption,
                    bounds=self._scene.bounds,
                    start_xy=np.asarray(start_xy, dtype=float),
                    goal_xy=np.asarray(goal_xy, dtype=float),
                )
                try:
                    path = plan_world_path(
                        scene_dict,
                        planning_grid,
                        start_xy,
                        goal_xy,
                        min_spacing=self._path_spacing,
                    )
                    self._last_planned_clearance = clearance
                    if clearance + 1e-9 < self._extra_clearance:
                        logger.warning(
                            "move path clearance reduced from %.3f m to %.3f m "
                            "because the generated map has no wider route",
                            self._extra_clearance,
                            clearance,
                        )
                    return path
                except RuntimeError as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            return None
        except Exception:
            logger.exception("A* planning failed")
            return None
