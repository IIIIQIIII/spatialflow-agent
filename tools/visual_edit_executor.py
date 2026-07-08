#!/usr/bin/env python3
import argparse
import base64
import io
import json
import os
import pathlib
import shutil
import time
import traceback
import urllib.error
import urllib.request

from PIL import Image

OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images"

MODELS = [
    "openai/gpt-image-2 via OpenRouter",
    "openai/gpt-5.4-image-2 via OpenRouter",
    "FLUX.2 [klein] 9B",
    "FLUX.2 [klein] 4B",
    "FLUX.2 [dev]",
    "FLUX.2 [max/pro/flex] via API if allowed",
    "Qwen-Image-Edit",
    "FLUX.1 Kontext/Fill fallback",
]


def read_json(path):
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def openrouter_key():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        return api_key
    default_env = pathlib.Path(__file__).resolve().parents[1] / ".env.openrouter"
    env_paths = [
        os.environ.get("SPATIALFLOW_OPENROUTER_ENV"),
        str(default_env),
    ]
    for env_path in [p for p in env_paths if p]:
        path = pathlib.Path(env_path)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("OPENROUTER_API_KEY is not set")


def prepare_image(path, max_side=1024):
    image = Image.open(path).convert("RGB")
    w, h = image.size
    scale = min(max_side / max(w, h), 1.0)
    nw = max(64, int(w * scale) // 16 * 16)
    nh = max(64, int(h * scale) // 16 * 16)
    if (nw, nh) != (w, h):
        image = image.resize((nw, nh), Image.Resampling.LANCZOS)
    return image


def image_data_url(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"


def prompt_from_plan(plan_path):
    plan = read_json(plan_path)
    goal = plan.get("goal") or plan.get("intent") or ""
    actions = plan.get("actions", [])
    feedback = plan.get("human_feedback") or {}
    action_text = "; ".join(
        a.get("name", "") + " " + json.dumps(a, ensure_ascii=False) for a in actions[:5]
    )
    feedback_text = ""
    if feedback:
        feedback_text = (
            " Human review corrections must override the initial plan. "
            f"Style correction: {', '.join(feedback.get('style_correction', []))}. "
            f"Strictly preserve: {', '.join(feedback.get('preserve', []))}. "
            f"Reduce: {', '.join(feedback.get('reduce', []))}. "
            f"Remove: {', '.join(feedback.get('remove', []))}. "
            f"Add: {', '.join(feedback.get('add', []))}. "
            f"Forbidden: {', '.join(feedback.get('forbid', []))}. "
        )
    return (
        "Transform this open-source empty room photo into a realistic Nordic / Scandinavian style living room. "
        "Preserve the exact camera viewpoint, window positions, wall geometry, floor material, and room structure. "
        "Add a light fabric sofa, wooden coffee table, neutral rug, subtle plants, warm natural lighting, and clean minimal decor. "
        "Do not change the windows, floor, ceiling, wall boundaries, or perspective. Avoid floating furniture and object intersections. "
        f"Goal: {goal}. Planned actions: {action_text}.{feedback_text}"
    )


def try_openrouter_image_model(model, image, prompt, output_path):
    payload = {
        "model": model,
        "prompt": (
            "Use the provided reference image as the exact room geometry. "
            "Keep camera viewpoint, windows, wall boundaries, floor color/material, ceiling, and perspective stable. "
            "Only stage the room visually according to the design instruction. "
            + prompt
        ),
        "input_references": [
            {
                "type": "image_url",
                "image_url": {"url": image_data_url(image)},
            }
        ],
        "quality": "high",
        "output_format": "png",
        "size": f"{image.width}x{image.height}",
        "n": 1,
    }
    req = urllib.request.Request(
        OPENROUTER_IMAGE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {openrouter_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://spatialflow.local",
            "X-Title": "SpatialFlow Design Agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc

    item = (body.get("data") or [{}])[0]
    b64 = item.get("b64_json")
    if not b64:
        raise RuntimeError(f"OpenRouter image response missing b64_json: {json.dumps(body)[:1000]}")
    output_path.write_bytes(base64.b64decode(b64))


def try_flux2_dev(image, prompt, output_path):
    import torch
    from diffusers import Flux2Pipeline

    pipe = Flux2Pipeline.from_pretrained(
        "black-forest-labs/FLUX.2-dev",
        torch_dtype=torch.bfloat16,
    )
    pipe.to("cuda")
    result = pipe(
        image=image,
        prompt=prompt,
        num_inference_steps=28,
        guidance_scale=4.0,
        generator=torch.Generator(device="cuda").manual_seed(42),
    ).images[0]
    result.save(output_path)


def try_flux2_klein_9b(image, prompt, output_path):
    import torch
    from diffusers import Flux2KleinPipeline

    pipe = Flux2KleinPipeline.from_pretrained(
        "black-forest-labs/FLUX.2-klein-9B",
        torch_dtype=torch.bfloat16,
    )
    pipe.to("cuda")
    result = pipe(
        image=image,
        prompt=prompt,
        height=image.height,
        width=image.width,
        guidance_scale=1.0,
        num_inference_steps=4,
        generator=torch.Generator(device="cuda").manual_seed(42),
    ).images[0]
    result.save(output_path)


def try_flux2_klein_4b(image, prompt, output_path):
    import torch
    from diffusers import Flux2KleinPipeline

    pipe = Flux2KleinPipeline.from_pretrained(
        "black-forest-labs/FLUX.2-klein-4B",
        torch_dtype=torch.bfloat16,
    )
    pipe.to("cuda")
    result = pipe(
        image=image,
        prompt=prompt,
        height=image.height,
        width=image.width,
        guidance_scale=1.0,
        num_inference_steps=4,
        generator=torch.Generator(device="cuda").manual_seed(42),
    ).images[0]
    result.save(output_path)


def model_plan(strategy):
    plans = {
        "interactive": [
            ("openai/gpt-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-image-2", image, prompt, output_path)),
            ("openai/gpt-5.4-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-5.4-image-2", image, prompt, output_path)),
            ("black-forest-labs/FLUX.2-klein-9B", try_flux2_klein_9b),
            ("black-forest-labs/FLUX.2-dev", try_flux2_dev),
            ("black-forest-labs/FLUX.2-klein-4B", try_flux2_klein_4b),
        ],
        "final": [
            ("openai/gpt-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-image-2", image, prompt, output_path)),
            ("openai/gpt-5.4-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-5.4-image-2", image, prompt, output_path)),
            ("black-forest-labs/FLUX.2-dev", try_flux2_dev),
            ("black-forest-labs/FLUX.2-klein-9B", try_flux2_klein_9b),
            ("black-forest-labs/FLUX.2-klein-4B", try_flux2_klein_4b),
        ],
        "openrouter": [
            ("openai/gpt-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-image-2", image, prompt, output_path)),
            ("openai/gpt-5.4-image-2", lambda image, prompt, output_path: try_openrouter_image_model("openai/gpt-5.4-image-2", image, prompt, output_path)),
        ],
        "klein-only": [
            ("black-forest-labs/FLUX.2-klein-9B", try_flux2_klein_9b),
            ("black-forest-labs/FLUX.2-klein-4B", try_flux2_klein_4b),
        ],
    }
    return plans.get(strategy, plans["interactive"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--metadata", required=True)
    ap.add_argument(
        "--strategy",
        default="interactive",
        choices=["interactive", "final", "openrouter", "klein-only"],
        help="interactive/final try openai/gpt-image-2 first; klein-only keeps the local fallback path.",
    )
    args = ap.parse_args()

    out_img = pathlib.Path(args.output)
    out_meta = pathlib.Path(args.metadata)
    out_img.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)

    image = prepare_image(args.image)
    prompt = prompt_from_plan(args.plan)
    attempts = []
    status = "failed"
    selected_model = None

    for model_name, fn in model_plan(args.strategy):
        started = time.time()
        try:
            fn(image, prompt, out_img)
            attempts.append({"model": model_name, "status": "ok", "seconds": round(time.time() - started, 3)})
            selected_model = model_name
            status = "ok"
            break
        except Exception as exc:
            attempts.append(
                {
                    "model": model_name,
                    "status": "failed",
                    "seconds": round(time.time() - started, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace_tail": traceback.format_exc().splitlines()[-8:],
                }
            )

    if status != "ok":
        src = pathlib.Path(args.image)
        if src.exists():
            shutil.copyfile(src, out_img)
        status = "failed_original_copied"

    data = {
        "stage": "generative_editing",
        "status": status,
        "target_models": MODELS,
        "selected_model": selected_model,
        "attempts": attempts,
        "strategy": args.strategy,
        "input_image": args.image,
        "plan": args.plan,
        "output_image": str(out_img),
        "prompt": prompt,
        "ts_unix": int(time.time()),
    }
    out_meta.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if status.startswith("failed"):
        raise SystemExit(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
