"""Player-owned EnvBackend adapter for semantic station overrides.

Skills communicate only with this adapter. The adapter is the player-owned
backend extension: it delegates normal motion and physics to the organizer
backend, owns object-instance alignment, and temporarily extends high-level
station metadata for auxiliary outputs. Any necessary simulator access stays
behind this backend boundary and never leaks into the skill layer.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np

from robot_agent.core.scene_context import SceneContext


@runtime_checkable
class CompetitionEnvBackend(Protocol):
    """Player-side extension of EnvBackend for physical manipulation.

    The organizer backend already exposes these methods.  Declaring the
    structural protocol here keeps skills dependent on capabilities rather
    than on ``RobosuiteBackend`` implementation fields.
    """

    def get_base_pose(self): ...
    def follow_path(self, path, **kwargs) -> bool: ...
    def set_physics_grasp_config(self, **kwargs) -> None: ...
    def grasp_object_physics(self, *args, **kwargs) -> bool: ...
    def place_object_physics(self, target: str, **kwargs) -> bool: ...


class SemanticBackendAdapter:
    """Delegate EnvBackend calls and own semantic station adaptation."""

    def __init__(self, delegate, scene_context: SceneContext) -> None:
        self._delegate = delegate
        self._scene = scene_context
        self._configured_checkpoint_path: str | None = None
        self._navigation_posture: dict[str, np.ndarray] | None = None

    @property
    def supports_physics_grasp(self) -> bool:
        return all(
            callable(getattr(self._delegate, name, None))
            for name in (
                "set_physics_grasp_config",
                "grasp_object_physics",
                "reset",
            )
        )

    def reset(self) -> None:
        self._delegate.reset()

    def close(self) -> None:
        self._delegate.close()

    def get_base_pose(self):
        return self._delegate.get_base_pose()

    def follow_path(self, path, **kwargs):
        return self._delegate.follow_path(path, **kwargs)

    def pick_object(self, target: str) -> bool:
        return bool(self._delegate.pick_object(target))

    def place_object(self, target: str) -> bool:
        return bool(self._delegate.place_object(target))

    def get_available_crates(self):
        return self._delegate.get_available_crates()

    def render(self) -> None:
        self._delegate.render()

    @property
    def action_spec(self):
        return self._delegate.action_spec

    @property
    def configured_checkpoint_path(self) -> str | None:
        return self._configured_checkpoint_path

    def set_physics_grasp_config(self, **kwargs) -> None:
        checkpoint = kwargs.get("checkpoint")
        checkpoint_text = str(checkpoint) if checkpoint is not None else None
        if checkpoint_text and checkpoint_text == self._configured_checkpoint_path:
            return
        self._delegate.set_physics_grasp_config(**kwargs)
        # The organizer backend constructs the policy before environment reset.
        # Re-run that public lifecycle here while no task action has executed,
        # ensuring every task-specific CPU policy gets the safe initialization
        # order without changing the protected backend implementation.
        self._delegate.reset()
        self._configured_checkpoint_path = checkpoint_text

    def grasp_object_physics(self, *args, **kwargs) -> bool:
        initial_pose = kwargs.get("initial_base_pose")
        object_name = kwargs.get("object_name")
        if self._navigation_posture is None:
            self._navigation_posture = self._capture_navigation_posture()
        # Snapshot unrelated movable bodies before *any* object-specific
        # near-field alignment.  The alignment itself is part of the grasp
        # transaction and must not be allowed to persistently disturb a later
        # object at the same source station.
        bystander_states = self._capture_bystander_states(
            str(object_name) if object_name else ""
        )
        if (
            isinstance(initial_pose, dict)
            and initial_pose.get("yaw") is not None
            and object_name
        ):
            from robot_agent.workflows.scripted_grasp_backend import (
                resolve_object_aligned_pose,
            )

            # One semantic station can contain several objects. Resolve the
            # selected instance's live offset here, inside the backend layer,
            # so the skill remains independent of MuJoCo state.
            aligned_pose = resolve_object_aligned_pose(
                self._delegate.env,
                str(object_name),
                float(initial_pose["yaw"]),
            )
            current_xy, _ = self._delegate.get_base_pose()
            alignment_path = self._final_alignment_path(
                current_xy,
                aligned_pose["xy"],
                float(aligned_pose["yaw"]),
            )
            if alignment_path and not self._delegate.follow_path(alignment_path):
                self._restore_bystander_states(bystander_states)
                return False
            self._align_navigation_yaw(float(aligned_pose["yaw"]))
            kwargs["initial_base_pose"] = aligned_pose
        elif isinstance(initial_pose, dict) and initial_pose.get("yaw") is not None:
            self._align_navigation_yaw(float(initial_pose["yaw"]))

        from robosuite.environments.factory_sorting import (
            load_factory_sorting_evalization as evaluation,
        )
        from robot_agent.workflows.scripted_grasp_backend import (
            run_dynamic_scripted_grasp,
        )

        original_runner = evaluation.run_factory_sorting_grasp_in_wrapped_env

        def backend_programmatic_runner(*runner_args, **runner_kwargs):
            env = runner_kwargs.get("env")
            if env is None and runner_args:
                env = runner_args[0]
            object_name = runner_kwargs.get("object_name")
            if not object_name:
                object_name = kwargs.get("object_name")
            if env is None or not object_name:
                raise RuntimeError(
                    "programmatic backend grasp requires env and object_name"
                )
            return run_dynamic_scripted_grasp(
                env,
                str(object_name),
                render=bool(runner_kwargs.get("render", False)),
                nav_env=self._delegate.env,
            )

        evaluation.run_factory_sorting_grasp_in_wrapped_env = (
            backend_programmatic_runner
        )
        try:
            return bool(self._delegate.grasp_object_physics(*args, **kwargs))
        finally:
            # Organizer grasp evaluation runs in a temporary environment and
            # synchronizes all material objects back to navigation. Isolate
            # that sandbox: only the selected target may carry state changes
            # across the backend call; unrelated objects retain their exact
            # pre-call physical state.
            self._restore_bystander_states(bystander_states)
            if (
                evaluation.run_factory_sorting_grasp_in_wrapped_env
                is backend_programmatic_runner
            ):
                evaluation.run_factory_sorting_grasp_in_wrapped_env = (
                    original_runner
                )

    def _capture_bystander_states(self, target_object: str) -> dict:
        from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
            base_robosuite_env,
        )

        raw = base_robosuite_env(self._delegate.env)
        states: dict[str, dict[str, np.ndarray | None]] = {}
        target_joints = {
            f"{target_object}_free",
            f"{target_object}_joint0",
        }
        # Capture every free joint, rather than trusting material_objects.
        # Some wrapped evaluation lifecycles rebuild that list while retaining
        # all free joints in the compiled model; model joints are therefore the
        # authoritative boundary for isolating unrelated movable bodies.
        for raw_joint_name in list(
            getattr(raw.sim.model, "joint_names", []) or []
        ):
            joint_name = (
                raw_joint_name.decode("utf-8")
                if isinstance(raw_joint_name, bytes)
                else str(raw_joint_name)
            )
            if joint_name in target_joints:
                continue
            try:
                joint_id = raw.sim.model.joint_name2id(joint_name)
                # MuJoCo enum mjJNT_FREE == 0.
                if int(raw.sim.model.jnt_type[joint_id]) != 0:
                    continue
                qpos = np.asarray(
                    raw.sim.data.get_joint_qpos(joint_name), dtype=float
                ).copy()
            except Exception:
                continue
            try:
                qvel = np.asarray(
                    raw.sim.data.get_joint_qvel(joint_name), dtype=float
                ).copy()
            except Exception:
                qvel = None
            states[joint_name] = {"qpos": qpos, "qvel": qvel}
        return states

    def _restore_bystander_states(self, states: dict) -> None:
        if not states:
            return
        from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
            base_robosuite_env,
        )

        raw = base_robosuite_env(self._delegate.env)
        for joint_name, state in states.items():
            raw.sim.data.set_joint_qpos(joint_name, state["qpos"])
            if state.get("qvel") is not None:
                try:
                    raw.sim.data.set_joint_qvel(joint_name, state["qvel"])
                except Exception:
                    pass
        raw.sim.forward()

    def _capture_navigation_posture(self) -> dict[str, np.ndarray]:
        """Capture the robot's pre-grasp compact upper-body posture."""
        from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
            base_robosuite_env,
        )

        raw = base_robosuite_env(self._delegate.env)
        robot = raw.robots[0]
        joint_names: list[str] = []
        joint_names.extend(getattr(robot, "robot_arm_joints", []) or [])
        joint_names.extend(getattr(robot.robot_model, "torso_joints", []) or [])
        joint_names.extend(getattr(robot.robot_model, "head_joints", []) or [])
        qpos_indexes = np.asarray(
            [raw.sim.model.get_joint_qpos_addr(name) for name in joint_names],
            dtype=int,
        )
        qvel_indexes = np.asarray(
            [raw.sim.model.get_joint_qvel_addr(name) for name in joint_names],
            dtype=int,
        )
        return {
            "qpos_indexes": qpos_indexes,
            "qvel_indexes": qvel_indexes,
            "qpos": np.asarray(raw.sim.data.qpos[qpos_indexes], dtype=float).copy(),
        }

    def _restore_navigation_posture(self, steps: int = 12) -> None:
        """Retract both arms after placement before the next base motion."""
        posture = self._navigation_posture
        if not posture:
            return
        from robosuite.environments.factory_sorting.load_factory_sorting_evalization import (
            base_robosuite_env,
        )

        raw = base_robosuite_env(self._delegate.env)
        qpos_indexes = posture["qpos_indexes"]
        qvel_indexes = posture["qvel_indexes"]
        start = np.asarray(raw.sim.data.qpos[qpos_indexes], dtype=float).copy()
        target = posture["qpos"]
        for step in range(max(1, int(steps))):
            alpha = float(step + 1) / float(max(1, int(steps)))
            raw.sim.data.qpos[qpos_indexes] = start + (target - start) * alpha
            raw.sim.data.qvel[qvel_indexes] = 0.0
            raw.sim.forward()

    @staticmethod
    def _final_alignment_path(current_xy, target_xy, yaw: float):
        """Move laterally first, then approach along the grasp heading."""
        current = np.asarray(current_xy, dtype=float).reshape(2)
        target = np.asarray(target_xy, dtype=float).reshape(2)
        forward = np.array([np.cos(yaw), np.sin(yaw)], dtype=float)
        delta = target - current
        forward_delta = forward * float(np.dot(delta, forward))
        lateral_waypoint = target - forward_delta
        path: list[np.ndarray] = []
        if np.linalg.norm(lateral_waypoint - current) > 0.01:
            path.append(lateral_waypoint)
        if np.linalg.norm(target - lateral_waypoint) > 0.01:
            path.append(target)
        return path

    def _align_navigation_yaw(self, target_yaw: float) -> None:
        """Align the navigation environment inside the backend adapter."""
        from robosuite.environments.factory_sorting.turn_to_station import (
            base_robosuite_env,
            get_base_world_pose,
            lock_base_xy,
            set_base_world_yaw_direct,
            shortest_angle,
            zero_base_velocity,
        )

        params_path = (
            Path(__file__).resolve().parents[3]
            / "knowledge"
            / "robot_params.json"
        )
        params = json.loads(params_path.read_text(encoding="utf-8"))
        turn = params.get("turn", {})
        tolerance = float(turn.get("tolerance", 0.02))
        max_iters = int(turn.get("max_iters", 8))
        raw = base_robosuite_env(self._delegate.env)
        robot = raw.robots[0]
        locked_xy, start_yaw = get_base_world_pose(raw, robot)
        if abs(shortest_angle(target_yaw - start_yaw)) > tolerance:
            set_base_world_yaw_direct(
                raw,
                robot,
                target_yaw=target_yaw,
                tolerance=min(tolerance, 1e-5),
                max_iters=max_iters,
            )
        lock_base_xy(raw, robot, locked_xy)
        zero_base_velocity(raw, robot)
        raw.sim.forward()

    def place_object_physics(
        self,
        target: str,
        *,
        station_override: dict[str, Any] | None = None,
    ) -> bool:
        with self._station_override(target, station_override):
            placed = bool(self._delegate.place_object_physics(target))
        if placed:
            self._restore_navigation_posture()
        return placed

    @contextmanager
    def _station_override(
        self,
        target: str,
        override: dict[str, Any] | None,
    ):
        if not override:
            yield
            return

        # ``env`` is the organizer backend's documented escape hatch.  This
        # adapter touches only its semantic port table, never MuJoCo state.
        env = self._delegate.env
        ports = getattr(env, "output_ports", None)
        if not isinstance(ports, dict):
            raise RuntimeError("backend output port metadata is unavailable")

        old_env_station = ports.get(target)
        scene_station = self._scene.output_ports.get(target)
        old_scene_center = None
        old_scene_approach = None
        if scene_station is not None:
            old_scene_center = np.asarray(scene_station.center, dtype=float).copy()
            old_scene_approach = (
                None
                if scene_station.approach is None
                else np.asarray(scene_station.approach, dtype=float).copy()
            )

        center = np.asarray(override["center"], dtype=float).reshape(-1)
        approach = np.asarray(override["approach"], dtype=float).reshape(-1)
        env_center = np.zeros(3, dtype=float)
        env_approach = np.zeros(3, dtype=float)
        env_center[: min(3, center.size)] = center[:3]
        env_approach[: min(3, approach.size)] = approach[:3]
        injected = {
            "name": target,
            "kind": str(override.get("kind") or "table"),
            "side": "output",
            "index": int(override.get("index", 0)),
            "center": env_center,
            "approach": env_approach,
            "semantic_map_adapter": True,
        }
        ports[target] = injected

        if scene_station is not None:
            scene_center = old_scene_center.copy()
            scene_center[:2] = env_center[:2]
            scene_approach = (
                np.zeros_like(scene_center)
                if old_scene_approach is None
                else old_scene_approach.copy()
            )
            scene_approach[:2] = env_approach[:2]
            scene_station.center = scene_center
            scene_station.approach = scene_approach

        try:
            yield
        finally:
            if old_env_station is None:
                if ports.get(target) is injected:
                    del ports[target]
            else:
                ports[target] = old_env_station
            if scene_station is not None and old_scene_center is not None:
                scene_station.center = old_scene_center
                scene_station.approach = old_scene_approach
