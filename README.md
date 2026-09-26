# 👨‍🍳 ChefMate — Professional Chef's Companion

A full-stack web app for chefs in big restaurants and hotels: world-cuisine recipe
database, location-personalised home page, guided step-by-step cooking mode with
timers, star reviews, and an AI sous-chef assistant with photo upload.

Built with **Flask + SQLite** (no other dependencies).

## 🚀 Quick start

```bash
pip install flask
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

- The SQLite database `chefmate.db` (users + reviews) is created automatically,
  and 49 recipes across 12 world cuisines are seeded on every start.
- **Register** with your address → city/country keywords decide which cuisines are
  shown first on your home page ("Popular near you").
- **Login** cross-checks email + hashed password against the users table.

## ✨ Features

| Feature | Where |
|---|---|
| Registration (name, role, restaurant, address, city, country) → stored in DB | `/register` |
| Login with database cross-check (hashed passwords) | `/login` |
| World recipe categories (Indian, Italian, Chinese, Mexican, Japanese, Thai, French, Mediterranean, American, Middle Eastern, Korean, Vietnamese) | `/` |
| Recipes filtered by the address given at signup | `/` (top section) |
| Search by dish or ingredient | `/` search bar |
| Full recipe: ingredients, spices, equipment, timed method | `/recipe/<id>` |
| **Start Cooking** → checklist (all materials + ingredients must be ticked) → one timed step at a time, tick "I completed this step" to advance | `/start/<id>` |
| Optional live countdown timer per step | cooking page |
| Star reviews + comments after finishing | recipe page / cooking finale |
| Profile (edit details, see your reviews) | `/profile` |
| Settings (change password, delete reviews) | `/settings` |
| AI sous-chef chat with image upload | `/assistant` |
| **Voice-to-text AI assistant** — floating mic button (every page incl. home): speak your question, see the live transcript, get a spoken + written answer | mic button 🎤 bottom-right |

## 🤖 AI assistant

Works in two modes:

1. **Offline knowledge engine (default, zero setup).** Understands:
   - any dish on the menu (full ingredient list + method),
   - ~25 classic kitchen problems (too salty, gravy splitting, rice sticky,
     sauce too thin, eggs scrambling, burnt garlic, dry chicken, cake sinking,
     bread not rising, steak temps, pasta, fish sticking, …),
   - spice and seasoning deep-dives (kasuri methi, doubanjiang, saffron, sumac, …),
   - "what can I cook with X" ingredient questions.

2. **Live vision-capable LLM (optional).** Set environment variables and the
   assistant routes to a real AI that can also analyse uploaded photos of pans,
   plates and textures:

   ```bash
   export CHEF_AI_API_KEY="sk-..."        # your OpenAI-compatible key
   export CHEF_AI_BASE_URL="https://api.openai.com/v1"   # optional
   export CHEF_AI_MODEL="gpt-4o-mini"     # optional, must be vision-capable
   python app.py
   ```

   No key is ever stored in the code — only read from the environment.

## 📁 Project structure

```
chefmate/
├── app.py              # Flask app: auth, DB, routes, AI assistant
├── recipes_data.py     # 49 recipes (ingredients/spices/equipment/timed steps)
├── static/voice.js     # voice-to-text AI assistant (mic + spoken replies)
├── chefmate.db         # created on first run (users, reviews)
├── templates/          # all pages (login, register, home, recipe, cooking…)
└── static/style.css    # the whole design
```

## 🔒 Notes

- Passwords are hashed with Werkzeug (PBKDF2); sessions are signed cookies.
- Change `CHEFMATE_SECRET_KEY` in production (`export CHEFMATE_SECRET_KEY=...`).
- To run on your network for the whole kitchen: `python app.py` then use the
  host machine's IP, or deploy behind gunicorn: `gunicorn -w 4 -b 0.0.0.0:8000 app:app`.
