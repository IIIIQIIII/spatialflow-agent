#!/usr/bin/env python3
import argparse
import base64
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-5.4"


def read_json(path, default=None):
    p = pathlib.Path(path)
    if not p.exists():
        return {} if default is None else default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def latest_run(project):
    output_dir = pathlib.Path(project) / "outputs"
    patterns = ["spatialflow-*", "default-run", "*"]
    runs = []
    for pattern in patterns:
        runs = sorted(
            [p for p in output_dir.glob(pattern) if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if runs:
            break
    if not runs:
        raise FileNotFoundError(f"no run directories found under {output_dir}")
    return runs[0]


def resolve_run(project, run):
    if run:
        p = pathlib.Path(run)
        if not p.is_absolute():
            p = pathlib.Path(project) / p
        return p
    return latest_run(project)


def image_data_url(path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    suffix = p.suffix.lower()
    mime = "image/jpeg" if suffix in [".jpg", ".jpeg"] else "image/png"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def openrouter_json(model, messages, temperature=0.1):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        default_env = pathlib.Path(__file__).resolve().parents[1] / ".env.openrouter"
        env_path = pathlib.Path(os.environ.get("SPATIALFLOW_OPENROUTER_ENV", str(default_env)))
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/openai/codex",
            "X-Title": "Codex SpatialFlow HITL Review",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
    content = body["choices"][0]["message"]["content"]
    cleaned = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def review_points(run_dir):
    spatial = read_json(run_dir / "room_spatial_parser.json")
    edit = read_json(run_dir / "visual_edit_executor.json")
    verifier = read_json(run_dir / "verification.json")
    plan = read_json(run_dir / "action_plan.json")
    masks = spatial.get("sam31_masks", {}).get("results", [])
    mask_counts = {item.get("prompt"): len(item.get("instances", [])) for item in masks}
    selected_edit_model = edit.get("selected_model")
    verdict = verifier.get("final_verdict", {})
    goal = plan.get("goal") or plan.get("intent") or ""
    input_image = edit.get("input_image") or spatial.get("input_image")
    if input_image and not pathlib.Path(input_image).is_absolute():
        input_image = str(run_dir.parent.parent / input_image)

    questions = [
        {
            "id": "style_target",
            "kind": "single_choice",
            "question": "当前 agent 把用户意图理解为 warm Nordic / Scandinavian living room，这个风格方向是否正确？",
            "options": [
                "accept_current_style",
                "more_premium_minimal",
                "warmer_family_living",
                "colder_gallery_style",
            ],
            "default": "accept_current_style",
            "why": "风格词会直接影响下一轮 prompt、家具密度、材质和灯光。",
        },
        {
            "id": "structure_preservation",
            "kind": "multi_select",
            "question": "哪些固定结构必须严格保持，不允许下一轮编辑改变？",
            "options": ["floor", "windows", "door", "wall_color", "ceiling_lights", "air_conditioner", "outlets"],
            "default": ["floor", "windows", "door", "ceiling_lights"],
            "why": "SAM3.1 mask 和 verifier 会把这些项作为 hard constraints。",
        },
        {
            "id": "density",
            "kind": "single_choice",
            "question": "当前家具密度是否符合预期？",
            "options": ["accept", "less_furniture_more_empty", "more_furnished", "only_key_furniture"],
            "default": "accept",
            "why": "SpatialFlow 场景里“太满/太空”是最常见的人类审美反馈。",
        },
        {
            "id": "objects",
            "kind": "multi_select",
            "question": "下一轮希望增加或减少哪些物体？",
            "options": ["reduce_plants", "remove_rug", "smaller_sofa", "add_floor_lamp", "add_wall_art", "keep_windows_unblocked"],
            "default": ["keep_windows_unblocked"],
            "why": "这些会被解析成 edit action，而不是停留在自然语言聊天。",
        },
        {
            "id": "acceptance",
            "kind": "single_choice",
            "question": "这个版本是否可以作为最终输出，还是进入 revision？",
            "options": ["accept_final", "revise_fast", "revise_and_final_render"],
            "default": "revise_fast",
            "why": "revise_fast 使用 FLUX.2-klein-9B；final render 可切回高质量模型。",
        },
    ]

    return {
        "stage": "human_review",
        "status": "needs_review",
        "review_model": "rule_based_fallback",
        "source_run": str(run_dir),
        "goal": goal,
        "current_result": {
            "input_image": input_image,
            "edited_image": str(run_dir / "edited_room.png"),
            "demo_html": str(run_dir / "demo.html"),
            "sam3_overlay": str(run_dir / "sam3_overlay.png"),
            "depth_visualization": str(run_dir / "depth_vis.png"),
            "edit_model": selected_edit_model,
            "verifier": verdict,
            "mask_counts": mask_counts,
        },
        "questions": questions,
        "recommended_next_action": "Ask the user to answer these review points. If they provide free-form feedback, run refine mode to convert it into feedback_revision.json and revised_action_plan.json.",
        "ts_unix": int(time.time()),
    }


def gpt54_review_points(run_dir, fallback):
    input_image = fallback["current_result"].get("input_image")
    images = [
        ("input_room", pathlib.Path(input_image) if input_image else None),
        ("edited_result", run_dir / "edited_room.png"),
        ("sam3_overlay", run_dir / "sam3_overlay.png"),
        ("depth_visualization", run_dir / "depth_vis.png"),
    ]
    content = [
        {
            "type": "text",
            "text": (
                "You are the human-in-the-loop review layer for a SpatialFlow spatial visual agent. "
                "Inspect the input room, edited result, SAM3 segmentation overlay, and depth visualization. "
                "Return ONLY valid JSON with this schema: "
                "{stage,status,review_model,source_run,current_result,questions,recommended_next_action,visual_critique,ts_unix}. "
                "questions must be a list of 4-7 objects with id, kind, question, options, default, why. "
                "Focus on user intent ambiguity, style, structure preservation, furniture density, blocked windows/doors, wall/floor preservation, and whether to accept or revise. "
                "The review must be specific to SpatialFlow virtual staging/interior visual workflows, not generic image critique. "
                f"Fallback state JSON: {json.dumps(fallback, ensure_ascii=False)}"
            ),
        }
    ]
    for label, path in images:
        if path is None:
            continue
        url = image_data_url(path)
        if url:
            content.append({"type": "text", "text": f"Image: {label}"})
            content.append({"type": "image_url", "image_url": {"url": url}})

    messages = [
        {
            "role": "system",
            "content": "You are a precise multimodal product reviewer. Output strict JSON only.",
        },
        {"role": "user", "content": content},
    ]
    data = openrouter_json(DEFAULT_MODEL, messages)
    data.setdefault("stage", "human_review")
    data.setdefault("status", "needs_review")
    data["review_model"] = DEFAULT_MODEL
    data["source_run"] = str(run_dir)
    data["ts_unix"] = int(time.time())
    return data


def parse_feedback(text):
    normalized = text.lower()
    revision = {
        "raw_feedback": text,
        "style_correction": [],
        "preserve": [],
        "reduce": [],
        "remove": [],
        "add": [],
        "forbid": [],
        "layout": [],
        "rerun_scope": "edit_only",
        "render_strategy": "interactive",
        "confidence": "rule_based",
    }

    patterns = [
        (r"高级|premium|luxury|更贵|质感", "style_correction", "more premium minimal"),
        (r"北欧|scandinavian|nordic", "style_correction", "keep Nordic / Scandinavian direction"),
        (r"冷静|克制|gallery|minimal|极简", "style_correction", "more restrained minimal composition"),
        (r"温暖|warm|家庭|cozy", "style_correction", "warmer cozy family living room"),
        (r"太满|拥挤|少一点|更空|less furniture|more empty", "reduce", "furniture density"),
        (r"植物.*少|少.*植物|不要植物|remove plants|reduce plants", "reduce", "plants"),
        (r"地毯.*不要|不要地毯|remove rug", "remove", "rug"),
        (r"沙发.*小|小一点.*沙发|smaller sofa", "reduce", "sofa size"),
        (r"落地灯|floor lamp", "add", "floor lamp"),
        (r"挂画|wall art|artwork", "add", "wall art"),
        (r"墙色|wall color", "preserve", "wall color"),
        (r"窗|window", "preserve", "windows"),
        (r"门|door", "preserve", "door"),
        (r"地板|floor", "preserve", "floor"),
        (r"不要挡窗|别挡窗|keep windows unblocked|unblock windows", "forbid", "blocking windows"),
        (r"不要改结构|preserve structure|结构保持", "preserve", "room structure"),
        (r"最终|final|高质量|quality", "render_strategy", "final"),
    ]
    for pattern, field, value in patterns:
        if re.search(pattern, normalized):
            if field == "render_strategy":
                revision[field] = value
            elif value not in revision[field]:
                revision[field].append(value)

    if revision["render_strategy"] == "final":
        revision["rerun_scope"] = "edit_and_verify"
    if not revision["preserve"]:
        revision["preserve"] = ["floor", "windows", "door", "room structure"]
    if not revision["style_correction"]:
        revision["style_correction"] = ["preserve original style direction unless contradicted by user"]
    return revision


def gpt54_parse_feedback(text, run_dir, fallback_revision):
    review = read_json(run_dir / "review_points.json", {})
    prompt = {
        "raw_feedback": text,
        "source_run": str(run_dir),
        "review_points": review,
        "rule_based_revision": fallback_revision,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You parse SpatialFlow visual-design human feedback into executable edit constraints. "
                "Return strict JSON only with keys: raw_feedback, style_correction, preserve, reduce, remove, add, forbid, layout, rerun_scope, render_strategy, confidence."
            ),
        },
        {
            "role": "user",
            "content": (
                "Convert this human feedback into structured revision JSON for a room virtual-staging agent. "
                "Use Chinese and English feedback accurately. Prefer concrete constraints over vague phrasing. "
                f"Input JSON: {json.dumps(prompt, ensure_ascii=False)}"
            ),
        },
    ]
    data = openrouter_json(DEFAULT_MODEL, messages)
    data.setdefault("raw_feedback", text)
    data.setdefault("rerun_scope", fallback_revision.get("rerun_scope", "edit_only"))
    data.setdefault("render_strategy", fallback_revision.get("render_strategy", "interactive"))
    data["confidence"] = DEFAULT_MODEL
    return data


def revise_plan(run_dir, feedback_revision):
    base = read_json(run_dir / "action_plan.json")
    if not base:
        base = {"stage": "agent_planning", "status": "contract_ready", "actions": []}
    actions = list(base.get("actions", []))
    actions.append(
        {
            "name": "apply_human_feedback",
            "source": "human_in_the_loop",
            "style_correction": feedback_revision.get("style_correction", []),
            "preserve": feedback_revision.get("preserve", []),
            "reduce": feedback_revision.get("reduce", []),
            "remove": feedback_revision.get("remove", []),
            "add": feedback_revision.get("add", []),
            "forbid": feedback_revision.get("forbid", []),
            "rerun_scope": feedback_revision.get("rerun_scope", "edit_only"),
        }
    )
    base["status"] = "revised_by_human_feedback"
    base["actions"] = actions
    base["human_feedback"] = feedback_revision
    base["ts_unix"] = int(time.time())
    return base


def interaction_state(run_dir, review, feedback_revision=None, revised_plan_path=None):
    versions = [
        {
            "version": "v1",
            "run_dir": str(run_dir),
            "edited_image": str(run_dir / "edited_room.png"),
            "verification": str(run_dir / "verification.json"),
            "status": "awaiting_human_review" if feedback_revision is None else "reviewed",
        }
    ]
    if feedback_revision is not None:
        versions.append(
            {
                "version": "v2_planned",
                "parent": "v1",
                "revised_plan": str(revised_plan_path),
                "status": "ready_for_fast_rerun",
                "recommended_edit_strategy": feedback_revision.get("render_strategy", "interactive"),
            }
        )
    return {
        "stage": "interaction_state",
        "status": "open" if feedback_revision is None else "revision_ready",
        "source_run": str(run_dir),
        "review_points": str(run_dir / "review_points.json"),
        "feedback_revision": str(run_dir / "feedback_revision.json") if feedback_revision is not None else None,
        "versions": versions,
        "pending_user_decision": feedback_revision is None,
        "ts_unix": int(time.time()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--run")
    ap.add_argument("--feedback")
    ap.add_argument("--feedback-file")
    ap.add_argument("--out-dir")
    ap.add_argument("--review-model", default=DEFAULT_MODEL)
    ap.add_argument("--no-model-review", action="store_true")
    args = ap.parse_args()

    run_dir = resolve_run(args.project, args.run)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else run_dir
    if not out_dir.is_absolute():
        out_dir = pathlib.Path(args.project) / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    review = review_points(run_dir)
    if not args.no_model_review:
        try:
            review = gpt54_review_points(run_dir, review)
        except Exception as exc:
            review["review_model_error"] = f"{type(exc).__name__}: {exc}"
    write_json(out_dir / "review_points.json", review)

    feedback_text = args.feedback
    if args.feedback_file:
        feedback_text = pathlib.Path(args.feedback_file).read_text(encoding="utf-8")

    if feedback_text:
        revision = parse_feedback(feedback_text)
        if not args.no_model_review:
            try:
                revision = gpt54_parse_feedback(feedback_text, out_dir, revision)
            except Exception as exc:
                revision["model_parse_error"] = f"{type(exc).__name__}: {exc}"
        write_json(out_dir / "feedback_revision.json", revision)
        revised = revise_plan(run_dir, revision)
        revised_plan_path = out_dir / "revised_action_plan.json"
        write_json(revised_plan_path, revised)
        state = interaction_state(run_dir, review, revision, revised_plan_path)
        write_json(out_dir / "interaction_state.json", state)
        print(json.dumps({"status": "revision_ready", "out_dir": str(out_dir), "revised_plan": str(revised_plan_path)}, ensure_ascii=False))
    else:
        state = interaction_state(run_dir, review)
        write_json(out_dir / "interaction_state.json", state)
        print(json.dumps({"status": "needs_review", "out_dir": str(out_dir), "review_points": str(out_dir / "review_points.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
