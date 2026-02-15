---
description: Deploy changes to the DigitalOcean Droplet
---

# Deploy to Droplet

Always deploy to the Droplet — never test locally.

1. Commit and push changes to `main`:
```bash
git add -A && git commit -m "<message>" && git push origin main
```

// turbo
2. Deploy to the Droplet:
```bash
bash install.sh --update
```

This will:
- SCP the `.env` to the Droplet
- `git pull origin main` on the Droplet
- `docker compose up -d --build` to rebuild and restart the container
- Verify the container is running
