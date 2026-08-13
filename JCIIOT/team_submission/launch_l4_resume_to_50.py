from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = Path(r"D:\tool\anaconda3\envs\jci_clean\python.exe")
CONFIG_PATH = (
    PROJECT_ROOT
    / "team_submission"
    / "training_configs"
    / "factory_sorting_l4_upper_bc_resume_to_50.json"
)
LOG_ROOT = PROJECT_ROOT / "team_submission" / "training_runs"
ACTIVE_RUN_PATH = LOG_ROOT / "l4_training_active.json"


def main() -> None:
    if not PYTHON_EXE.is_file():
        raise FileNotFoundError(PYTHON_EXE)
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(CONFIG_PATH)

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout_path = LOG_ROOT / f"l4_resume_to_50_{stamp}.stdout.log"
    stderr_path = LOG_ROOT / f"l4_resume_to_50_{stamp}.stderr.log"

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.Popen(
            [
                str(PYTHON_EXE),
                "-u",
                "-m",
                "robomimic.scripts.train",
                "--config",
                str(CONFIG_PATH),
                "--resume",
            ],
            cwd=PROJECT_ROOT,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    run_info = {
        "pid": process.pid,
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "resume_from_epoch": 12,
        "target_epoch": 50,
        "config": str(CONFIG_PATH),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    ACTIVE_RUN_PATH.write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(run_info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
