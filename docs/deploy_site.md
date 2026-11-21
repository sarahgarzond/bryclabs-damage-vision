# Demo website on GitHub Pages

The site in `site/` is static (HTML, CSS, JS). GitHub Pages hosts it for free. The model runs
separately (AWS or Colab) behind `app/api.py`, and the site calls it from the browser.

## 1. Turn on GitHub Pages (once)
Repo → Settings → Pages → Build and deployment → Source: **GitHub Actions**.
Every push to `main` that changes `site/` redeploys automatically (workflow `.github/workflows/pages.yml`).
The address is `https://sarahgarzond.github.io/bryclabs-damage-vision/`.
Pages on a private repo needs a paid plan, so the repo must be public for a free account.

## 2. Start the API next to the model

```bash
# AWS, with vLLM already serving on port 8000 (docs/aws_setup.md)
export DV_BACKEND=openai DV_BASE_URL=http://localhost:8000/v1 DV_COST_PER_HOUR=1.0
uvicorn app.api:app --host 0.0.0.0 --port 8080
```

```bash
# Colab (model loaded inside the API)
DV_BACKEND=hf DV_LOAD_4BIT=1 DV_RUNS=1 uvicorn app.api:app --port 8080 &
```

Check it: `curl http://localhost:8080/health`.

## 3. Give it an https address
GitHub Pages is https, and browsers block calls from an https page to a plain http API.
A free Cloudflare quick tunnel fixes this without an account:

```bash
curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared
./cloudflared tunnel --url http://localhost:8080
```

It prints an address like `https://something.trycloudflare.com`. The address changes every time you restart the tunnel.

## 4. Connect the site
Open the site, click the status button (top right), paste the address, click **Test**, then **Save**.
Or share a link that connects automatically:
`https://sarahgarzond.github.io/bryclabs-damage-vision/?api=https://something.trycloudflare.com`

## 5. Put real results on the site (before the pitch)
The bundled examples are illustrative drawings, clearly labelled as such. Replace them with real outputs:

```bash
python scripts/build_site.py --results outputs/final --images data/images \
  --pick img_004 img_017 img_052 --titles "Ceiling water stain" "Wall crack" "No damage" \
  --eval outputs/eval/main
git add site && git commit -m "Real examples and metrics on the site" && git push
```

Only publish images you are allowed to share (check the licence column in `data/images.csv`).
The examples work without the model, so the demo still works if the tunnel or GPU fails.

## Test locally

```bash
python -m http.server 8000 -d site                                   # site on http://localhost:8000
DV_BACKEND=mock DV_VERIFY=0 uvicorn app.api:app --port 8080          # fake model for UI testing
```

Then connect the site to `http://localhost:8080`. A plain http address works when the site itself is local.
