# tienelicencia.com: rules for anyone (or any agent) working in this repository

- netlify/edge-functions/site-hits.js is the Shifted Labs traffic counter. Never delete, move, rename or edit it, and never let a build, clean-up or refactor remove it. It is installed from a master copy: ~/.config/shiftedlabs/site-hits/install.sh ~/Documents/GitHub/tienelicencia
- Never delete or regenerate anything under netlify/edge-functions/: treat it as hand-installed. Don't edit the file by hand
  (changes are overwritten from the master copy; ask Shifted Labs). It deliberately has no database key: it reads
  SITE_HITS_KEY from the Netlify site's environment.
- Automated builds stage only their own output paths (site/data, netlify/functions/data), never `git add -A` or `git add .`.
- After deploying, https://tienelicencia.com/__sl/e should return a small JavaScript file (200), not a 404.
