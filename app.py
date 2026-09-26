"""
ChefMate — a professional chef's companion web app.
Flask + SQLite. Run:  python app.py   ->  http://127.0.0.1:5000

Features
  * Registration + login (passwords hashed, cross-checked against the DB)
  * Recipe database spanning world cuisines
  * Home page categories, filtered by the address given at signup
  * Full recipe pages with ingredients / spices / equipment
  * Guided cooking mode (checklist -> timed steps -> review)
  * Reviews with star ratings
  * AI sous-chef assistant with image upload.
    Set CHEF_AI_API_KEY (+ optional CHEF_AI_BASE_URL, CHEF_AI_MODEL) to
    use a live vision-capable LLM; otherwise a built-in offline chef
    knowledge engine answers.
"""
import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import recipes_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chefmate.db")

app = Flask(__name__)
app.secret_key = os.environ.get("CHEFMATE_SECRET_KEY", "chefmate-dev-secret-change-me")


# ----------------------------------------------------------------- database
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'Chef',
        restaurant TEXT DEFAULT '',
        address TEXT DEFAULT '',
        city TEXT DEFAULT '',
        country TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        cuisine TEXT NOT NULL,
        emoji TEXT DEFAULT '🍽️',
        description TEXT DEFAULT '',
        difficulty TEXT DEFAULT 'Medium',
        servings INTEGER DEFAULT 2,
        time_minutes INTEGER DEFAULT 30,
        details TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        rating INTEGER NOT NULL,
        comment TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    # seed recipes (refresh each start so recipe edits show up)
    c.execute("DELETE FROM recipes")
    for r in recipes_data.RECIPES:
        details = json.dumps({"ingredients": r["ingredients"], "steps": r["steps"]})
        c.execute("INSERT INTO recipes (id, name, cuisine, emoji, description, difficulty, servings, time_minutes, details) VALUES (?,?,?,?,?,?,?,?,?)",
                   (r["id"], r["name"], r["cuisine"], r["emoji"], r["description"],
                    r["difficulty"], r["servings"], r["time_minutes"], details))
    conn.commit()
    conn.close()


def recipe_to_dict(row):
    r = dict(row)
    details = json.loads(r.pop("details"))
    r["ingredients"] = details["ingredients"]
    r["steps"] = details["steps"]
    return r


# ----------------------------------------------------------------- helpers
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warn")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def avg_rating(recipe_id):
    conn = get_db()
    row = conn.execute("SELECT AVG(rating) a, COUNT(*) n FROM reviews WHERE recipe_id = ?", (recipe_id,)).fetchone()
    conn.close()
    if not row or not row["n"]:
        return 0.0, 0
    return round(row["a"], 1), row["n"]


# ----------------------------------------------------------------- routes
@app.route("/")
def home():
    user = current_user()
    q = (request.args.get("q") or "").strip()
    cuisine = (request.args.get("cuisine") or "").strip()

    conn = get_db()
    rows = conn.execute("SELECT * FROM recipes").fetchall()
    conn.close()
    recipes = [recipe_to_dict(r) for r in rows]

    if q:
        ql = q.lower()
        recipes = [r for r in recipes if ql in r["name"].lower() or ql in r["description"].lower()
                   or any(ql in i["name"].lower() for i in r["ingredients"])]
    if cuisine:
        recipes = [r for r in recipes if r["cuisine"] == cuisine]

    enriched = []
    for r in recipes:
        r["avg"], r["n_reviews"] = avg_rating(r["id"])
        enriched.append(r)

    local_cuisines = []
    if user:
        addr = " ".join([user.get("address", ""), user.get("city", ""), user.get("country", "")])
        local_cuisines = recipes_data.cuisines_for_address(addr)
    for_you = [r for r in enriched if r["cuisine"] in local_cuisines]

    return render_template("index.html", user=user, recipes=enriched, for_you=for_you,
                           categories=recipes_data.CATEGORIES, q=q, cuisine=cuisine,
                           local_cuisines=local_cuisines)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        role = (request.form.get("role") or "Chef").strip()
        restaurant = (request.form.get("restaurant") or "").strip()
        address = (request.form.get("address") or "").strip()
        city = (request.form.get("city") or "").strip()
        country = (request.form.get("country") or "").strip()

        if not name or not email or not password:
            flash("Name, email and password are required.", "error")
        elif not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Please enter a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users (name, email, password_hash, role, restaurant, address, city, country, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (name, email, generate_password_hash(password), role, restaurant,
                     address, city, country, datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                uid = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
                conn.close()
                session["user_id"] = uid
                flash(f"Welcome to ChefMate, Chef {name.split()[0]}! 🧑‍🍳", "success")
                return redirect(url_for("home"))
            except sqlite3.IntegrityError:
                flash("An account with this email already exists. Please log in.", "error")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    return render_template("register.html", user=current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            flash(f"Welcome back, Chef {row['name'].split()[0]}!", "success")
            nxt = request.args.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else url_for("home"))
        flash("Invalid email or password — please cross-check and try again.", "error")
    return render_template("login.html", user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out. See you on the next service!", "success")
    return redirect(url_for("home"))


@app.route("/recipe/<int:recipe_id>")
def recipe_detail(recipe_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    r = recipe_to_dict(row)
    reviews = [dict(x) for x in conn.execute(
        """SELECT rv.*, u.name FROM reviews rv JOIN users u ON u.id = rv.user_id
           WHERE rv.recipe_id = ? ORDER BY rv.created_at DESC""", (recipe_id,)).fetchall()]
    conn.close()
    r["avg"], r["n_reviews"] = avg_rating(recipe_id)
    user = current_user()
    my_review = next((v for v in reviews if user and v["user_id"] == user.get("id")), None)
    return render_template("recipe.html", r=r, reviews=reviews, user=user, my_review=my_review)


@app.route("/recipe/<int:recipe_id>/review", methods=["POST"])
@login_required
def add_review(recipe_id):
    rating = int(request.form.get("rating", 0))
    comment = (request.form.get("comment") or "").strip()
    if not (1 <= rating <= 5):
        flash("Please choose a star rating.", "error")
    else:
        conn = get_db()
        conn.execute("DELETE FROM reviews WHERE recipe_id = ? AND user_id = ?", (recipe_id, session["user_id"]))
        conn.execute("INSERT INTO reviews (recipe_id, user_id, rating, comment, created_at) VALUES (?,?,?,?,?)",
                     (recipe_id, session["user_id"], rating, comment, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
        flash("Thanks for the review! 🌟", "success")
    return redirect(url_for("recipe_detail", recipe_id=recipe_id))


@app.route("/start/<int:recipe_id>")
@login_required
def start_cooking(recipe_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return render_template("cooking.html", r=recipe_to_dict(row), user=current_user())


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        conn.execute("UPDATE users SET name=?, role=?, restaurant=?, address=?, city=?, country=? WHERE id=?",
                     (f.get("name", "").strip(), f.get("role", "Chef").strip(), f.get("restaurant", "").strip(),
                      f.get("address", "").strip(), f.get("city", "").strip(), f.get("country", "").strip(),
                      session["user_id"]))
        conn.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))
    user = dict(conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone())
    stats = dict(conn.execute("""SELECT COUNT(*) n, ROUND(AVG(rating),1) avg FROM reviews WHERE user_id=?""",
                              (session["user_id"],)).fetchone())
    recent = [dict(x) for x in conn.execute(
        """SELECT rv.rating, rv.comment, rv.created_at, re.name, re.emoji, re.id rid
           FROM reviews rv JOIN recipes re ON re.id = rv.recipe_id
           WHERE rv.user_id = ? ORDER BY rv.created_at DESC LIMIT 5""", (session["user_id"],)).fetchall()]
    conn.close()
    return render_template("profile.html", user=user, stats=stats, recent=recent)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        conn = get_db()
        if action == "password":
            old = request.form.get("old_password") or ""
            new = request.form.get("new_password") or ""
            row = conn.execute("SELECT password_hash FROM users WHERE id=?", (session["user_id"],)).fetchone()
            if not check_password_hash(row["password_hash"], old):
                flash("Current password is incorrect.", "error")
            elif len(new) < 6:
                flash("New password must be at least 6 characters.", "error")
            else:
                conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (generate_password_hash(new), session["user_id"]))
                conn.commit()
                flash("Password changed.", "success")
            conn.close()
            return redirect(url_for("settings"))
        elif action == "delete_reviews":
            conn.execute("DELETE FROM reviews WHERE user_id=?", (session["user_id"],))
            conn.commit()
            conn.close()
            flash("All your reviews were deleted.", "success")
            return redirect(url_for("settings"))
        conn.close()
    return render_template("settings.html", user=current_user())


@app.route("/assistant")
def assistant():
    return render_template("assistant.html", user=current_user())


# ------------------------------------------------------- AI sous-chef engine
TROUBLESHOOTING = {
    "splitting": "Gravy or sauce splitting? The emulsion broke — stabilise it: take it off the flame, whisk in 1-2 tbsp cold cream or yogurt (tempered first with a spoon of the hot sauce), or a cornstarch slurry (1 tsp : 2 tbsp cold water), and re-whisk over LOW heat. Never boil after adding dairy. To prevent it: full-fat dairy, low flame, and temper the dairy before it meets the pot.",
    "split": "Gravy or sauce splitting? The emulsion broke — stabilise it: take it off the flame, whisk in 1-2 tbsp cold cream or yogurt (tempered first with a spoon of the hot sauce), or a cornstarch slurry (1 tsp : 2 tbsp cold water), and re-whisk over LOW heat. Never boil after adding dairy.",
    "salty": "Too salty? Fix by bulking with a starchy neutral (potato, rice, unsalted stock) or dairy (cream/yogurt) which coats the tongue. Balance with a squeeze of acid (lemon/lime/vinegar) — acid tricks the palate into perceiving less salt. Never add water alone; it just thins.",
    "spicy": "Over-spiced? Dairy (yogurt, cream, coconut milk), a little sugar or honey, and nut butters all capsaicin. Serve with rice or bread. Do NOT add more water.",
    "bland": "Bland usually means missing salt, acid or fat — not more spice. Season in layers, finish with acid (lemon/vinegar), and mount with butter or good olive oil off the heat.",
    "burnt": "If it smells burnt but isn't black: immediately transfer the GOOD portion to a clean pan WITHOUT scraping the bottom, add a peeled raw potato or a slice of bread for 10 minutes to absorb the acrid note, and mask with a little fat and acid. If it's truly carbonised, start over.",
    "thin": "Sauce too thin? Reduce on a wide, hard simmer — evaporation is a technique. Or thicken: cornstarch slurry (1 tsp : 2 tbsp cold water, always cold), beurre manié, or a cream/nut paste for Indian gravies.",
    "thick": "Too thick? Loosen with hot stock or pasta water, never cold water — hot liquid keeps the emulsion intact.",
    "rice": "Rice sticky? Rinse until the water runs clear before cooking, use 1 : 1.5 rice-to-water for aged basmati, rest 5 minutes off-heat, then fluff with a fork — never stir mid-cook. Already sticky? Spread on a tray, fan it, use for fried rice.",
    "curry": "For a deeper curry: bloom whole spices in hot fat FIRST (30 seconds, never burn), fry onions properly (8-12 min to golden, not glassy), and cook the tomato base until the fat visibly separates at the edges — that's the sign the rawness is gone.",
    "egg": "Eggs scrambling in carbonara/custard? The pan is too hot. Off the flame entirely, add a splash of cold pasta water/milk, and pour the egg mixture in a thin stream while tossing constantly.",
    "bitter": "Bitter note? Balance with salt, a pinch of sugar, and fat. Burnt garlic is the usual culprit — add garlic AFTER the onion has softened, never first in hot oil.",
    "oily": "Dish feels greasy? Skim the top with a spoon, blot with a paper towel laid on the surface for 2 seconds, or refrigerate and lift the solidified fat. For stir-fries, drain on a rack, never paper (it steams).",
    "undercooked": "Undercooked in the middle but browning outside? Lower the heat, cover to trap steam (braise effect), and add a splash of liquid. For meats, verify with a thermometer: chicken 74°C, pork 63°C, salmon 52-54°C for medium.",
    "overcooked": "Overcooked meat? Slice thin against the grain, nap with a moist sauce or jus, and serve on a warm plate. Rescue overcooked vegetables by puréeing into a soup with stock and cream.",
    "dry chicken": "Dry chicken breast? Next time brine 30 min in 5% salt water, pull at 65-70°C and rest 5 minutes. Right now: slice thin and serve with a sauce or gravy.",
    "cake": "Cake sinking in the middle? Three usual causes: oven door opened before 75% of bake time, underbaked centre, or too much leavening/liquid. Test with a skewer at the centre and add 5-10 minutes if wet. For a sunken cake already baked: level it, soak with syrup, and use it as a trifle or cake-pop base.",
    "bread": "Bread problems — dense & heavy: the yeast died (water above 46°C) or under-proved; dough should double and pass the poke test (dent springs back slowly). Pale crust: add steam for the first 10 minutes. Gummy crumb: under-baked — internal temp should read 93-96°C.",
    "steak": "Perfect steak: dry the surface, salt 40 min ahead (or just before, never 5-10 min ahead), screaming-hot pan. Flip every minute for an even crust. Pull 5°C below target (rare 49°C, medium-rare 52°C, medium 57°C, well 65°C) and rest HALF the cooking time. Grey band = heat too low; raw centre = pan too cold.",
    "pasta": "Perfect pasta: water like the sea (7 g salt / litre), never add oil. Pull 1-2 minutes before al dente and finish IN the sauce with a splash of pasta water — the starch binds the sauce to the noodle. Fresh pasta needs only 90 seconds to 2 minutes.",
    "fish": "Fish sticking to the pan? Three rules: fish bone-dry, pan properly hot, and DON'T touch it for 2-3 minutes — it releases itself when the crust forms. Force it early and the skin tears. Confident flip once, baste with butter.",
}

SPICE_NOTES = {
    "garam masala": "Warm North-Indian blend (cardamom, clove, cinnamon, cumin, coriander, black pepper). Add at the END of cooking — it's an aroma spice, not a cooking spice.",
    "kasuri methi": "Dried fenugreek leaves — the signature butter-chicken finish. Always crush between palms to release its maple-like aroma.",
    "saffron": "Bloom in warm (not boiling) liquid for 10 minutes. A pinch colours and perfumes a whole pot. Never stir hard.",
    "turmeric": "Earthary-earthy, mostly for colour and a background bitterness. 1/4-1/2 tsp is almost always enough; too much makes a dish medicinal.",
    "cumin": "Nutty earth. Bloom whole seeds in hot fat until they dance and darken one shade; ground cumin goes in with the tomato/onion base.",
    "sichuan peppercorn": "Citrus-pine aroma plus the má numbing tingle. Toast dry, grind fresh, and add at the end — heat destroys the buzz.",
    "sumac": "Tangy, crimson, lemony Middle-Eastern garnish — always raw over salads and shawarma, never cooked.",
    "fish sauce": "Southeast Asian salt+umami. Never taste it from the bottle — in the hot broth it melts into savoury depth. Balance with palm sugar and tamarind/lime.",
    "doubanjiang": "Fermented Sichuan chilli-bean paste. Must be fried slowly in oil until it turns the oil red — raw, it's harsh and salty.",
    "paprika": "Sweet Hungarian for colour; smoked Spanish (pimentón) for depth. Burns fast — bloom briefly, off high heat.",
    "gochujang": "Korean fermented chilli-soybean paste — sweet, savoury and gently hot all at once. Fry it in oil for 30 seconds to bloom it, or thin with sesame oil and honey into a glaze. Do not taste raw from the tub.",
}


def _local_assistant_reply(message, history):
    msg = message.lower()
    conn = get_db()
    rows = conn.execute("SELECT * FROM recipes").fetchall()
    conn.close()
    recipes = [recipe_to_dict(r) for r in rows]

    # 1) direct troubleshooting keywords
    for key, answer in TROUBLESHOOTING.items():
        if key in msg:
            return answer

    # 2) spice knowledge
    for key, note in SPICE_NOTES.items():
        if key in msg:
            return f"{note} Ask me for a substitute if you're missing it."

    # 3) a specific recipe the chef is working on
    STOP = {"the", "and", "with", "how", "make", "cook", "recipe", "for", "best",
            "style", "alla", "classic", "street", "sauce", "dish", "need", "help"}
    def _score(r):
        words = [w for w in r["name"].lower().split("(")[0].split() if len(w) >= 3 and w not in STOP and not w.isdigit()]
        tokens = msg.split()
        return sum(1 for w in words if w in tokens)
    scored = [(_score(r), -len(r["name"]), r) for r in recipes]
    scored = [s for s in scored if s[0] >= 1 and s[1] <= -6]  # prefer distinctive names
    if scored:
        scored.sort(key=lambda s: (-s[0], s[1]))
        best = scored[0][2]
        r = best
        ings = ", ".join(f"{i['name']} ({i['qty']})" for i in r["ingredients"])
        steps = "\n".join(f"  {i+1}. {s['text']} (~{s['minutes']} min)"
                           for i, s in enumerate(r["steps"]))
        return (f"**{r['name']}** ({r['cuisine']}, {r['time_minutes']} min, serves {r['servings']}):\n\n"
                f"**Everything you need:** {ings}\n\n**Method:**\n{steps}\n\n"
                f"Tell me which step is troubling you, or describe (or show) what went wrong and I'll help.")

    # 4) ingredient-based suggestion
    matches = [r for r in recipes if any(i["name"].lower() in msg for i in r["ingredients"])]
    if matches:
        names = ", ".join(r["name"] for r in matches[:4])
        return f"With that you could cook: {names}. Say the dish name and I'll walk you through it step by step."

    return ("I'm your offline sous-chef. I can help with: a specific dish from the menu (say its name), "
            "an ingredient you have on hand, a cooking problem (too salty / burnt / sauce won't thicken / "
            "rice sticky...), or spice guidance. For full image analysis of your pan, ask the admin to "
            "connect a live AI key (see README) — meanwhile, describe what you see and I'll diagnose it.")


def _live_ai_reply(message, history, image_data_url=None):
    """Call an OpenAI-compatible vision-capable chat API. Key comes from the
    CHEF_AI_API_KEY environment variable — never hardcoded."""
    api_key = os.environ.get("CHEF_AI_API_KEY")
    if not api_key:
        return None
    base = os.environ.get("CHEF_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("CHEF_AI_MODEL", "gpt-4o-mini")

    recipe_names = ", ".join(r["name"] for r in recipes_data.RECIPES)
    system = ("You are ChefMate, an expert AI sous-chef assisting professional chefs in restaurants "
              "and hotels. You know world cuisines, spices, techniques and food science in depth. "
              "Be concise, precise and practical; give temperatures, times and quantities. "
              f"The app's current menu includes: {recipe_names}. If the chef uploads a photo, "
              "analyse what you can see (dish state, colour, texture, problems) and advise.")

    messages = [{"role": "system", "content": system}]
    for h in (history or [])[-8:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        if h.get("text"):
            messages.append({"role": role, "content": h["text"]})
    if image_data_url:
        messages.append({"role": "user", "content": [
            {"type": "text", "text": message or "What's wrong with what's in this photo? Please advise."},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]})
    else:
        messages.append({"role": "user", "content": message})

    body = json.dumps({"model": model, "messages": messages, "max_tokens": 700}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


@app.route("/api/assistant", methods=["POST"])
def assistant_api():
    """Open to everyone — the sous-chef helps even before you register."""
    message = (request.json.get("message") or "").strip()
    history = request.json.get("history") or []
    image_data_url = request.json.get("image") or None
    if not message and not image_data_url:
        return jsonify(ok=False, error="Say something to your sous-chef!"), 400
    try:
        reply = _live_ai_reply(message, history, image_data_url)
    except Exception as e:
        reply = None
        app.logger.warning("Live AI failed (%s); falling back to offline engine.", e)
    if reply is None:
        reply = _local_assistant_reply(message or "", history)
    return jsonify(ok=True, reply=reply)


@app.context_processor
def inject_user():
    return dict(current_user=current_user())


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
