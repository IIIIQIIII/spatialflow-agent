#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_step(name, command, workdir, env, log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    started = time.time()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(
            command,
            cwd=workdir,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
    return {
        "name": name,
        "command": command,
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 3),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "status": "ok" if proc.returncode == 0 else "failed",
    }


def artifact(path):
    p = pathlib.Path(path)
    return str(p)


def relpath(from_dir, target):
    return os.path.relpath(str(target), str(from_dir))


def copy_tree(src, dst):
    src = pathlib.Path(src)
    dst = pathlib.Path(dst)
    if not src.exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def summary_html(run_root, bundle):
    base_dir = pathlib.Path(bundle["paths"]["base"])
    hitl_dir = pathlib.Path(bundle["paths"].get("hitl", ""))
    review_dir = pathlib.Path(bundle["paths"].get("review", ""))
    input_image = pathlib.Path(bundle["input_image"])
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SpatialFlow Run Summary</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; margin: 32px; color: #111827; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin: 20px 0 32px; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; }}
    img {{ width: 100%; border-radius: 8px; border: 1px solid #e5e7eb; background: #f9fafb; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f9fafb; border-radius: 8px; padding: 12px; }}
    ul {{ line-height: 1.6; }}
  </style>
</head>
<body>
  <h1>SpatialFlow Full Run</h1>
  <p>{bundle["goal"]}</p>
  <div class="grid">
    <div class="card"><h2>Input</h2><img src="{relpath(run_root, input_image)}" alt="input" /></div>
    <div class="card"><h2>Segmentation</h2><img src="{relpath(run_root, base_dir / "sam3_overlay.png")}" alt="segmentation" /></div>
    <div class="card"><h2>Depth</h2><img src="{relpath(run_root, base_dir / "depth_vis.png")}" alt="depth" /></div>
    <div class="card"><h2>Edit V1</h2><img src="{relpath(run_root, base_dir / "edited_room.png")}" alt="v1" /></div>
  </div>
  <div class="card">
    <h2>Base run</h2>
    <ul>
      <li>Run id: {bundle["run_id"]}</li>
      <li>Planner: {bundle["models"]["planner"]}</li>
      <li>Edit model v1: {bundle["models"].get("edit_v1") or "n/a"}</li>
      <li>Verifier verdict v1: {bundle["verdicts"].get("v1")}</li>
    </ul>
  </div>
"""
    if review_dir.exists():
        html += f"""
  <div class="card">
    <h2>Review</h2>
    <pre>{json.dumps(bundle.get("review", {}), ensure_ascii=False, indent=2)}</pre>
  </div>
"""
    if hitl_dir.exists() and (hitl_dir / "edited_room.png").exists():
        html += f"""
  <div class="grid">
    <div class="card"><h2>Edit V2</h2><img src="{relpath(run_root, hitl_dir / "edited_room.png")}" alt="v2" /></div>
    <div class="card">
      <h2>Human Feedback</h2>
      <pre>{json.dumps(bundle.get("revision", {}), ensure_ascii=False, indent=2)}</pre>
    </div>
  </div>
"""
    html += "</body></html>\n"
    return html


def build_smoke_run(repo_root, run_root, run_id, config, image_path):
    sample_root = repo_root / "demo-data" / "default-run"
    base_dir = run_root / "base"
    review_dir = run_root / "review"
    hitl_dir = run_root / "hitl-v2"
    copied = {
        "base": copy_tree(sample_root / "base", base_dir),
        "review": copy_tree(sample_root / "review", review_dir),
        "hitl": copy_tree(sample_root / "hitl-v2", hitl_dir),
    }
    steps = [
        {
            "name": "smoke_sample_materialization",
            "command": ["copy", "demo-data/default-run", str(run_root)],
            "returncode": 0 if copied["base"] else 1,
            "seconds": 0.0,
            "stdout_path": None,
            "stderr_path": None,
            "status": "ok" if copied["base"] else "failed",
            "mode": "smoke-test",
        }
    ]
    trace = {
        "run_id": run_id,
        "mode": "smoke-test",
        "config": str(repo_root / "configs" / "spatialflow-agent.json"),
        "input_image": str(image_path),
        "steps": steps,
        "ts_unix": int(time.time()),
    }
    write_json(run_root / "trace.json", trace)

    review = read_json(review_dir / "review_points.json") if (review_dir / "review_points.json").exists() else {}
    revision = read_json(hitl_dir / "feedback_revision.json") if (hitl_dir / "feedback_revision.json").exists() else {}
    base_verify = read_json(base_dir / "verification.json") if (base_dir / "verification.json").exists() else {}
    hitl_verify = read_json(hitl_dir / "verification.json") if (hitl_dir / "verification.json").exists() else {}
    base_edit = read_json(base_dir / "visual_edit_executor.json") if (base_dir / "visual_edit_executor.json").exists() else {}
    hitl_edit = read_json(hitl_dir / "visual_edit_executor.json") if (hitl_dir / "visual_edit_executor.json").exists() else {}

    bundle = {
        "product_name": config.get("product_name"),
        "run_id": run_id,
        "mode": "smoke-test",
        "goal": config.get("goal"),
        "input_image": str(image_path),
        "paths": {
            "base": str(base_dir),
            "review": str(review_dir),
            "hitl": str(hitl_dir),
        },
        "models": {
            "planner": config.get("model"),
            "edit_v1": base_edit.get("selected_model"),
            "edit_v2": hitl_edit.get("selected_model"),
        },
        "verdicts": {
            "v1": (base_verify.get("final_verdict") or {}).get("label"),
            "v2": (hitl_verify.get("final_verdict") or {}).get("label"),
        },
        "review": review,
        "revision": revision,
        "trace_path": str(run_root / "trace.json"),
        "ts_unix": int(time.time()),
    }
    write_json(run_root / "bundle.json", bundle)
    (run_root / "demo.html").write_text(summary_html(run_root, bundle), encoding="utf-8")
    return {
        "status": "ok" if copied["base"] else "failed",
        "mode": "smoke-test",
        "run_root": str(run_root),
        "trace": str(run_root / "trace.json"),
        "bundle": str(run_root / "bundle.json"),
        "demo": str(run_root / "demo.html"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/spatialflow-agent.json")
    ap.add_argument("--image", default="inputs/room-dataset.png")
    ap.add_argument("--run-id")
    ap.add_argument("--feedback")
    ap.add_argument("--strategy", default="interactive", choices=["interactive", "final", "openrouter", "klein-only"])
    ap.add_argument("--smoke-test", action="store_true", help="Materialize a full run from bundled sample artifacts without requiring models or APIs.")
    args = ap.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    config_path = repo_root / args.config
    image_path = repo_root / args.image
    config = read_json(config_path)
    default_prefix = "spatialflow-smoke" if args.smoke_test else "spatialflow"
    run_id = args.run_id or f"{default_prefix}-{int(time.time())}"
    run_root = repo_root / "outputs" / run_id
    if run_root.exists():
        shutil.rmtree(run_root)

    if args.smoke_test:
        result = build_smoke_run(repo_root, run_root, run_id, config, image_path)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    base_dir = run_root / "base"
    review_dir = run_root / "review"
    hitl_dir = run_root / "hitl-v2"
    log_dir = base_dir / "tool-logs"
    base_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SPATIALFLOW_OUTPUT_DIR"] = str(base_dir)

    steps = []
    config_steps = [
        ("room_spatial_parser", ["python3", "tools/room_spatial_parser.py", "--image", str(image_path), "--output", str(base_dir / "room_spatial_parser.json")]),
        ("depth_layout_estimator", ["python3", "tools/depth_layout_estimator.py", "--image", str(image_path), "--spatial", str(base_dir / "room_spatial_parser.json"), "--output", str(base_dir / "depth_layout.json")]),
        ("layout_action_planner", ["python3", "tools/layout_action_planner.py", "--config", str(config_path), "--spatial", str(base_dir / "room_spatial_parser.json"), "--layout", str(base_dir / "depth_layout.json"), "--output", str(base_dir / "action_plan.json")]),
        ("visual_edit_executor", ["python3", "tools/visual_edit_executor.py", "--image", str(image_path), "--plan", str(base_dir / "action_plan.json"), "--output", str(base_dir / "edited_room.png"), "--metadata", str(base_dir / "visual_edit_executor.json"), "--strategy", args.strategy]),
        ("visual_verifier", ["python3", "tools/visual_verifier.py", "--before", str(image_path), "--after", str(base_dir / "edited_room.png"), "--spatial", str(base_dir / "room_spatial_parser.json"), "--layout", str(base_dir / "depth_layout.json"), "--output", str(base_dir / "verification.json")]),
    ]

    for name, command in config_steps:
        step = run_step(name, command, repo_root, env, log_dir)
        steps.append(step)
        if step["returncode"] != 0:
            break

    review = {}
    revision = {}
    if all(step["returncode"] == 0 for step in steps):
        review_step = run_step(
            "hitl_review",
            ["python3", "tools/hitl_review.py", "--project", str(repo_root), "--run", str(base_dir), "--out-dir", str(review_dir)],
            repo_root,
            env,
            review_dir / "tool-logs",
        )
        steps.append(review_step)
        if (review_dir / "review_points.json").exists():
            review = read_json(review_dir / "review_points.json")

        if args.feedback:
            feedback_step = run_step(
                "hitl_feedback",
                [
                    "python3",
                    "tools/hitl_review.py",
                    "--project",
                    str(repo_root),
                    "--run",
                    str(base_dir),
                    "--out-dir",
                    str(hitl_dir),
                    "--feedback",
                    args.feedback,
                ],
                repo_root,
                env,
                hitl_dir / "tool-logs",
            )
            steps.append(feedback_step)
            if feedback_step["returncode"] == 0:
                hitl_steps = [
                    (
                        "visual_edit_executor_v2",
                        [
                            "python3",
                            "tools/visual_edit_executor.py",
                            "--image",
                            str(image_path),
                            "--plan",
                            str(hitl_dir / "revised_action_plan.json"),
                            "--output",
                            str(hitl_dir / "edited_room.png"),
                            "--metadata",
                            str(hitl_dir / "visual_edit_executor.json"),
                            "--strategy",
                            args.strategy,
                        ],
                    ),
                    (
                        "visual_verifier_v2",
                        [
                            "python3",
                            "tools/visual_verifier.py",
                            "--before",
                            str(image_path),
                            "--after",
                            str(hitl_dir / "edited_room.png"),
                            "--spatial",
                            str(base_dir / "room_spatial_parser.json"),
                            "--layout",
                            str(base_dir / "depth_layout.json"),
                            "--output",
                            str(hitl_dir / "verification.json"),
                        ],
                    ),
                ]
                for name, command in hitl_steps:
                    steps.append(run_step(name, command, repo_root, env, hitl_dir / "tool-logs"))
                if (hitl_dir / "feedback_revision.json").exists():
                    revision = read_json(hitl_dir / "feedback_revision.json")

    trace = {
        "run_id": run_id,
        "config": str(config_path),
        "input_image": str(image_path),
        "steps": steps,
        "ts_unix": int(time.time()),
    }
    write_json(run_root / "trace.json", trace)

    base_verify = read_json(base_dir / "verification.json") if (base_dir / "verification.json").exists() else {}
    hitl_verify = read_json(hitl_dir / "verification.json") if (hitl_dir / "verification.json").exists() else {}
    base_edit = read_json(base_dir / "visual_edit_executor.json") if (base_dir / "visual_edit_executor.json").exists() else {}
    hitl_edit = read_json(hitl_dir / "visual_edit_executor.json") if (hitl_dir / "visual_edit_executor.json").exists() else {}

    bundle = {
        "product_name": config.get("product_name"),
        "run_id": run_id,
        "goal": config.get("goal"),
        "input_image": str(image_path),
        "paths": {
            "base": str(base_dir),
            "review": str(review_dir),
            "hitl": str(hitl_dir),
        },
        "models": {
            "planner": config.get("model"),
            "edit_v1": base_edit.get("selected_model"),
            "edit_v2": hitl_edit.get("selected_model"),
        },
        "verdicts": {
            "v1": (base_verify.get("final_verdict") or {}).get("label"),
            "v2": (hitl_verify.get("final_verdict") or {}).get("label"),
        },
        "review": review,
        "revision": revision,
        "trace_path": str(run_root / "trace.json"),
        "ts_unix": int(time.time()),
    }
    write_json(run_root / "bundle.json", bundle)
    (run_root / "demo.html").write_text(summary_html(run_root, bundle), encoding="utf-8")

    print(json.dumps({"status": "ok", "run_root": str(run_root), "trace": str(run_root / "trace.json"), "bundle": str(run_root / "bundle.json")}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
