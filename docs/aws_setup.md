# GPU setup (AWS from BrycLabs, or any 24 GB GPU)

## 1. Ask Lukas for
One GPU instance with 24 GB GPU memory (g5.xlarge with A10G or g6.xlarge with L4), about 100 GB disk, Ubuntu Deep Learning AMI, SSH access, until Sunday evening. Note the hourly price for the efficiency report.

## 2. Serve the model with vLLM

```bash
python3 -m venv ~/vllm && source ~/vllm/bin/activate
pip install -U vllm
vllm serve Qwen/Qwen2.5-VL-7B-Instruct --max-model-len 16384 --limit-mm-per-prompt '{"image": 1}' --port 8000
```

Older vLLM versions take `--limit-mm-per-prompt image=1`. Try `Qwen/Qwen3-VL-8B-Instruct` if your vLLM version supports it, and keep whichever works.

Check it from the same machine:

```bash
curl http://localhost:8000/v1/models
```

## 3. Run the pipeline (second terminal)

```bash
git clone https://github.com/sarahgarzond/bryclabs-damage-vision && cd bryclabs-damage-vision
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-gpu.txt
export DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1 DV_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
python scripts/run.py --images data/images --out outputs/qwen7b --runs 3 --cost-per-hour 1.0 --limit 3
```

Replace `--cost-per-hour` with the real instance price. Remove `--limit 3` once the first three outputs look right.

## 4. Let teammates use it
Do not open port 8000 to the internet. Use an SSH tunnel from each laptop:

```bash
ssh -L 8000:localhost:8000 ubuntu@<instance-ip>
```

Then on the laptop: `DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1 python app/app.py`.

## Colab / Kaggle fallback (no AWS yet)
Open `notebooks/colab_quickstart.ipynb` on a GPU runtime. It uses the `hf` backend with `--load-4bit` so the 7B model fits on a 16 GB T4.
