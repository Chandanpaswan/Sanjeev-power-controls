# Deployment Guide

## Local preview
Open `index.html` in a browser or use VS Code Live Server.

## GitHub
1. Create a repository named `sanjeev-power-controls`.
2. Open a terminal in this project folder.
3. Run:

```bash
git init
git add .
git commit -m "Initial commit: Sanjeev Power Controls website"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/sanjeev-power-controls.git
git push -u origin main
```

## GitHub Pages
1. Open the repository on GitHub.
2. Go to Settings → Pages.
3. Choose deployment from the `main` branch and `/ (root)`.
4. Save and wait for GitHub Pages to publish.
5. Add a custom domain only after configuring DNS and HTTPS.

## Before launch
- Replace the placeholder email in `js/main.js`.
- Add verified company phone, email, address, and domain.
- Replace demo product categories with actual products.
- Add real product and factory photographs.
- Test all links and mobile layouts.
- The contact form uses `mailto:` and is not a server-side form.
