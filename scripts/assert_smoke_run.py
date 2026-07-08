#!/usr/bin/env python3
import json
import pathlib
import sys


REQUIRED_FILES = [
    "trace.json",
    "bundle.json",
    "demo.html",
    "base/room_spatial_parser.json",
    "base/depth_layout.json",
    "base/depth_vis.png",
    "base/edited_room.png",
    "base/sam3_overlay.png",
    "base/verification.json",
    "base/visual_edit_executor.json",
    "review/review_points.json",
    "review/interaction_state.json",
    "hitl-v2/feedback_revision.json",
    "hitl-v2/revised_action_plan.json",
    "hitl-v2/verification.json",
]


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        fail("usage: assert_smoke_run.py <run_root>")

    run_root = pathlib.Path(sys.argv[1])
    if not run_root.exists():
        fail(f"run root does not exist: {run_root}")

    missing = [item for item in REQUIRED_FILES if not (run_root / item).exists()]
    if missing:
        fail("missing required smoke artifacts:\n" + "\n".join(missing))

    trace = json.loads((run_root / "trace.json").read_text(encoding="utf-8"))
    bundle = json.loads((run_root / "bundle.json").read_text(encoding="utf-8"))
    review = json.loads((run_root / "review" / "review_points.json").read_text(encoding="utf-8"))

    if trace.get("mode") != "smoke-test":
        fail("trace.json mode is not smoke-test")
    if not trace.get("steps"):
        fail("trace.json has no steps")
    if bundle.get("mode") != "smoke-test":
        fail("bundle.json mode is not smoke-test")
    if "verdicts" not in bundle:
        fail("bundle.json missing verdicts")
    if not review.get("questions"):
        fail("review_points.json missing questions")

    demo_html = (run_root / "demo.html").read_text(encoding="utf-8")
    for needle in ["SpatialFlow Full Run", "Base run", "Review"]:
        if needle not in demo_html:
            fail(f"demo.html missing expected text: {needle}")

    print(json.dumps({"status": "ok", "run_root": str(run_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
