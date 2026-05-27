# dist/

Ovaj folder sadrži `tacx_app_latest.zip` — uvijek aktualnu verziju aplikacije.

Auto-update u `main.py` preuzima ovaj zip pri svakom ažuriranju.

**Ne commitaj zip direktno** — koristi GitHub Actions ili ručno pri svakom releaseu:
1. Spakuj projekt: `zip -r dist/tacx_app_latest.zip . --exclude dist/ --exclude .git/`
2. `git add dist/tacx_app_latest.zip`
3. `git commit -m "Release vX.XX"`
4. `git push`
