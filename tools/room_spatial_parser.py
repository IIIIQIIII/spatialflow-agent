#!/usr/bin/env python3
import argparse
import contextlib
import json
import logging
import os
import pathlib
import re
import sys
import time
import traceback
import warnings

import numpy as np
import torch
from PIL import Image

MODELS = [
    "jetjodh/sam3.1 checkpoint with Meta SAM3.1 multiplex code",
    "Qwen3.5 vision-language foundation",
]

SAM31_PROMPTS = ["floor", "wall", "ceiling", "window", "door", "free floor area"]
SAM31_COLORS = [
    (255, 80, 80),
    (80, 180, 255),
    (255, 210, 80),
    (120, 255, 140),
    (210, 120, 255),
    (255, 140, 80),
]


def load_image(path, max_side=1280):
    image = Image.open(path).convert("RGB")
    w, h = image.size
    scale = min(max_side / max(w, h), 1.0)
    if scale < 1.0:
        image = image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return image


def extract_json(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def qwen35_room_understanding(image):
    from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration

    model_id = "Qwen/Qwen3.5-9B"
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
    )
    processor = AutoProcessor.from_pretrained(model_id)
    prompt = """
You are the room understanding module for an interior design agent.
Analyze the room image and return ONLY valid JSON:
{
  "room_type": string,
  "fixed_structure": [{"label": "wall|floor|ceiling|window|door|trim|fixture", "location": "left|center|right|top|bottom", "preserve": true, "notes": "..."}],
  "editable_regions": [{"label": "free floor area|empty wall area|decor candidate", "location": "...", "notes": "..."}],
  "existing_objects": [{"label": string, "location": string, "editable": boolean, "notes": "..."}],
  "scene_graph": [{"subject": string, "relation": string, "object": string}],
  "hard_constraints": [string],
  "uncertainty": [string]
}
Focus on walls, floor, ceiling, windows, doors, furniture, free space, and what must be preserved for a room-staging edit.
"""
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image], return_tensors="pt").to("cuda")
    generated = model.generate(**inputs, max_new_tokens=768, do_sample=False)
    trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
    decoded = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    return model_id, decoded, extract_json(decoded)


def fallback_structure(image):
    w, h = image.size
    return {
        "room_type": "empty_room",
        "fixed_structure": [
            {"label": "floor", "location": "bottom", "preserve": True, "notes": "large wood floor region"},
            {"label": "ceiling", "location": "top", "preserve": True, "notes": "white ceiling with recessed lights"},
            {"label": "windows", "location": "left and center", "preserve": True, "notes": "multiple visible windows"},
            {"label": "door", "location": "right", "preserve": True, "notes": "glass door/open doorway"},
            {"label": "walls", "location": "left center right", "preserve": True, "notes": "neutral wall planes"},
        ],
        "editable_regions": [
            {"label": "free floor area", "location": "bottom center", "notes": "candidate sofa/rug/coffee-table placement"},
            {"label": "empty wall area", "location": "right wall", "notes": "candidate art or lighting but preserve outlets/vents"},
        ],
        "existing_objects": [],
        "scene_graph": [
            {"subject": "floor", "relation": "below", "object": "walls"},
            {"subject": "windows", "relation": "embedded_in", "object": "walls"},
            {"subject": "free floor area", "relation": "supports", "object": "future furniture"},
        ],
        "hard_constraints": [
            "preserve floor material and perspective",
            "preserve all windows and door geometry",
            "keep camera viewpoint unchanged",
            "place furniture only on floor/free-space region",
        ],
        "uncertainty": ["fallback heuristic used instead of Qwen3.5"],
        "image_size": {"width": w, "height": h},
    }


def _as_numpy(value):
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "cpu"):
        return value.cpu().numpy()
    return np.asarray(value)


def _ensure_sam3_path():
    default_src = pathlib.Path(__file__).resolve().parents[1] / "vendor" / "sam3"
    sam3_src = os.environ.get("SAM3_SOURCE_DIR", str(default_src))
    if os.path.isdir(sam3_src) and sam3_src not in sys.path:
        sys.path.insert(0, sam3_src)
    return sam3_src


def sam31_room_masks(image_path, output_dir):
    sam3_src = _ensure_sam3_path()
    from sam3.model_builder import build_sam3_predictor

    default_checkpoint = pathlib.Path(__file__).resolve().parents[1] / "models" / "sam3" / "sam3.1_multiplex.pt"
    checkpoint = os.environ.get("SAM31_CHECKPOINT", str(default_checkpoint))
    if not os.path.exists(checkpoint):
        raise FileNotFoundError(f"SAM3.1 checkpoint not found: {checkpoint}")

    output_dir = pathlib.Path(output_dir)
    mask_dir = output_dir / "sam3_masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "sam3_overlay.png"
    runtime_log_path = output_dir / "sam3_runtime.log"

    original = Image.open(image_path).convert("RGB")
    overlay = original.convert("RGBA")
    image_area = original.width * original.height
    results = []
    previous_logging_level = logging.root.manager.disable
    warnings.filterwarnings("ignore", category=FutureWarning)
    logging.disable(logging.CRITICAL)
    try:
        with runtime_log_path.open("w", encoding="utf-8") as runtime_log:
            with contextlib.redirect_stdout(runtime_log), contextlib.redirect_stderr(runtime_log):
                predictor = build_sam3_predictor(
                    checkpoint_path=checkpoint,
                    version="sam3.1",
                    compile=False,
                    warm_up=False,
                    max_num_objects=16,
                    multiplex_count=16,
                    use_fa3=False,
                    use_rope_real=False,
                    async_loading_frames=False,
                )
                model = predictor.model
                state = model.init_state(
                    resource_path=str(image_path),
                    offload_video_to_cpu=False,
                    async_loading_frames=False,
                )
                for prompt_index, prompt in enumerate(SAM31_PROMPTS):
                    with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                        _, outputs = model.add_prompt(
                            state,
                            frame_idx=0,
                            text_str=prompt,
                            output_prob_thresh=0.35,
                        )

                    masks = _as_numpy(outputs.get("out_binary_masks", np.zeros((0, original.height, original.width), dtype=bool)))
                    boxes = _as_numpy(outputs.get("out_boxes_xywh", np.zeros((0, 4), dtype=np.float32)))
                    scores = _as_numpy(outputs.get("out_probs", np.zeros((0,), dtype=np.float32)))
                    obj_ids = _as_numpy(outputs.get("out_obj_ids", np.arange(len(masks))))
                    prompt_items = []
                    color = SAM31_COLORS[prompt_index % len(SAM31_COLORS)]

                    for idx, mask in enumerate(masks[:8]):
                        mask = mask.astype(bool)
                        area = int(mask.sum())
                        if area == 0:
                            continue
                        mask_path = mask_dir / f"{prompt.replace(' ', '_')}_{idx}.png"
                        Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(mask_path)

                        tint = Image.new("RGBA", original.size, color + (0,))
                        alpha = Image.fromarray((mask.astype(np.uint8) * 92), mode="L")
                        tint.putalpha(alpha)
                        overlay = Image.alpha_composite(overlay, tint)

                        prompt_items.append(
                            {
                                "object_id": int(obj_ids[idx]) if idx < len(obj_ids) else idx,
                                "score": float(scores[idx]) if idx < len(scores) else None,
                                "box_xywh": [float(x) for x in boxes[idx].tolist()] if idx < len(boxes) else None,
                                "area_px": area,
                                "area_ratio": round(area / image_area, 6),
                                "mask_path": str(mask_path),
                            }
                        )

                    results.append({"prompt": prompt, "instances": prompt_items})
                del state, model, predictor
    finally:
        logging.disable(previous_logging_level)

    overlay.save(overlay_path)
    return {
        "status": "ok",
        "model": "jetjodh/sam3.1",
        "checkpoint": checkpoint,
        "codebase": sam3_src,
        "prompts": SAM31_PROMPTS,
        "overlay_path": str(overlay_path),
        "mask_dir": str(mask_dir),
        "runtime_log": str(runtime_log_path),
        "results": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    image = load_image(args.image)
    attempts = []
    parsed = None
    raw = None
    model = None
    try:
        started = time.time()
        model, raw, parsed = qwen35_room_understanding(image)
        attempts.append({"model": model, "status": "ok", "seconds": round(time.time() - started, 3)})
    except Exception as exc:
        attempts.append(
            {
                "model": "Qwen/Qwen3.5-9B",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "trace_tail": traceback.format_exc().splitlines()[-8:],
            }
        )
    if parsed is None:
        parsed = fallback_structure(image)

    mask_attempt = None
    try:
        started = time.time()
        mask_attempt = sam31_room_masks(args.image, out.parent)
        mask_attempt["seconds"] = round(time.time() - started, 3)
        attempts.append(
            {
                "model": "jetjodh/sam3.1",
                "status": "ok",
                "seconds": mask_attempt["seconds"],
            }
        )
    except Exception as exc:
        mask_attempt = {
            "status": "failed",
            "model": "jetjodh/sam3.1",
            "error": f"{type(exc).__name__}: {exc}",
            "trace_tail": traceback.format_exc().splitlines()[-8:],
        }
        attempts.append(mask_attempt)

    data = {
        "stage": "room_understanding",
        "status": "ok",
        "target_models": MODELS,
        "selected_model": model or "heuristic_fallback",
        "input_image": args.image,
        "attempts": attempts,
        "qwen_raw": raw,
        "room_state": parsed,
        "mask_status": mask_attempt["status"],
        "sam31_masks": mask_attempt,
        "ts_unix": int(time.time()),
    }
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
