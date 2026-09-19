import json
import sys
import os

def convert_wf(input_path, output_path, model_name=None, thresh=0.20):
    with open(input_path, "r", encoding="utf-8") as f:
        wf = json.load(f)

    if model_name:
        for nid, node in wf.items():
            if node.get("class_type") == "UNETLoader":
                node["inputs"]["unet_name"] = model_name

    unet_loader_id = None
    lora_id = None
    clip_id = None
    video_vae_id = None
    audio_vae_id = None
    sampler_id = None
    total_steps = 4

    for nid, node in wf.items():
        ctype = node.get("class_type")
        if ctype == "UNETLoader":
            unet_loader_id = nid
        elif ctype in ("LoraLoaderBypassModelOnly", "LoraLoaderModelOnly", "LoraLoader"):
            lora_id = nid
        elif ctype == "CLIPLoader":
            clip_id = nid
        elif ctype == "VAELoader":
            vae_name = node.get("inputs", {}).get("vae_name", "")
            if "video" in vae_name:
                video_vae_id = nid
            elif "audio" in vae_name:
                audio_vae_id = nid
        elif ctype == "MiniMaxH3DualClockSamplerT8":
            sampler_id = nid
            total_steps = node.get("inputs", {}).get("steps", 4)

    existing_ids = set(wf.keys())
    def get_new_id(base_num):
        num = base_num
        while str(num) in existing_ids:
            num += 1
        existing_ids.add(str(num))
        return str(num)

    tc_id = get_new_id(101)
    sel_model_id = get_new_id(102)
    sel_clip_id = get_new_id(103)
    sel_vvae_id = get_new_id(104)
    sel_avae_id = get_new_id(105)

    model_source_id = lora_id if lora_id else unet_loader_id

    # Add TeaCache Node
    wf[tc_id] = {
        "class_type": "MiniMaxH3TeaCache",
        "inputs": {
            "model": [model_source_id, 0],
            "rel_l1_thresh": float(thresh),
            "start_step": 1,
            "end_step": -1,
            "total_steps": int(total_steps)
        }
    }

    # Add SelectModelDevice -> gpu:1
    wf[sel_model_id] = {
        "class_type": "SelectModelDevice",
        "inputs": {
            "model": [tc_id, 0],
            "device": "gpu:1"
        }
    }

    # Re-route sampler to use sel_model_id
    if sampler_id and sampler_id in wf:
        wf[sampler_id]["inputs"]["model"] = [sel_model_id, 0]

    # Add SelectCLIPDevice -> gpu:0
    if clip_id:
        wf[sel_clip_id] = {
            "class_type": "SelectCLIPDevice",
            "inputs": {
                "clip": [clip_id, 0],
                "device": "gpu:0"
            }
        }
        for nid, node in wf.items():
            if nid == sel_clip_id:
                continue
            inputs = node.get("inputs", {})
            for k, v in inputs.items():
                if isinstance(v, list) and len(v) == 2 and v[0] == clip_id:
                    inputs[k] = [sel_clip_id, 0]

    # Add SelectVAEDevice -> gpu:0 for video VAE
    if video_vae_id:
        wf[sel_vvae_id] = {
            "class_type": "SelectVAEDevice",
            "inputs": {
                "vae": [video_vae_id, 0],
                "device": "gpu:0"
            }
        }
        for nid, node in wf.items():
            if nid == sel_vvae_id:
                continue
            inputs = node.get("inputs", {})
            for k, v in inputs.items():
                if isinstance(v, list) and len(v) == 2 and v[0] == video_vae_id:
                    inputs[k] = [sel_vvae_id, 0]

    # Add SelectVAEDevice -> gpu:0 for audio VAE
    if audio_vae_id:
        wf[sel_avae_id] = {
            "class_type": "SelectVAEDevice",
            "inputs": {
                "vae": [audio_vae_id, 0],
                "device": "gpu:0"
            }
        }
        for nid, node in wf.items():
            if nid == sel_avae_id:
                continue
            inputs = node.get("inputs", {})
            for k, v in inputs.items():
                if isinstance(v, list) and len(v) == 2 and v[0] == audio_vae_id:
                    inputs[k] = [sel_avae_id, 0]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print(f"[OK] Converted {input_path} -> {output_path}")

if __name__ == "__main__":
    inp = sys.argv[1]
    out = sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "None" else None
    thresh = float(sys.argv[4]) if len(sys.argv) > 4 else 0.20
    convert_wf(inp, out, model, thresh)
