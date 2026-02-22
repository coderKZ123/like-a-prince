import streamlit as st

st.set_page_config(page_title="War Game", layout="centered")

# --- Session state ---
if "size" not in st.session_state:
    st.session_state.size = 5
if "selected" not in st.session_state:
    st.session_state.selected = None
if "turn" not in st.session_state:
    st.session_state.turn = "Red"
if "placements" not in st.session_state:
    # {(r,c): {"team": "Red", "type": "Mine", "emoji": "⛏️"}}
    st.session_state.placements = {}

def reset():
    st.session_state.selected = None
    st.session_state.turn = "Red"
    st.session_state.placements = {}

# --- Simple mapping: card -> what appears on the board ---
CARD_TO_STRUCTURE = {
    "Miner":  {"type": "Mine",            "emoji": "⛏️"},
    "Melee":  {"type": "Melee Barracks",  "emoji": "⚔️"},
    "Archer": {"type": "Archer Barracks", "emoji": "🏹"},
    "Tower":  {"type": "Tower",           "emoji": "🗼"},
}

# --- CSS for colored cards ---
st.markdown(
    """
    <style>
      .unit-card {
        border-radius: 14px;
        padding: 14px 14px;
        border: 2px solid rgba(0,0,0,0.12);
        margin: 0px 0px;
      }
      .unit-title { font-size: 18px; font-weight: 800; margin: 0; }
      .unit-sub { font-size: 12px; opacity: 0.85; margin-top: 6px; }
      .red { background: rgba(255, 0, 0, 0.10); border-color: rgba(255, 0, 0, 0.35); }
      .blue { background: rgba(0, 120, 255, 0.10); border-color: rgba(0, 120, 255, 0.35); }
      .tiny { font-size: 11px; opacity: 0.8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Header ---
st.title("War Game (Dummy UI)")
st.caption("Click a square → pick a card → it becomes a building/unit.")

with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Reset"):
        reset()
    if st.button("➡️ Next Turn"):
        st.session_state.turn = "Blue" if st.session_state.turn == "Red" else "Red"
    st.divider()
    st.write("Turn:")
    st.subheader(st.session_state.turn)

st.write("### Board")
st.info("Pick a square first. Then choose Miner/Melee/Archer/Tower to place something there.")

# --- Helpers ---
def square_label(r, c):
    """What the board shows on each square."""
    data = st.session_state.placements.get((r, c))
    if not data:
        return "·"
    team = data["team"]
    team_initial = "R" if team == "Red" else "B"
    return f"{team_initial}{data['emoji']}"

def place_structure(card_name: str):
    """Place the selected card's structure on the selected square."""
    if st.session_state.selected is None:
        return
    r, c = st.session_state.selected
    info = CARD_TO_STRUCTURE[card_name]
    st.session_state.placements[(r, c)] = {
        "team": st.session_state.turn,
        "type": info["type"],
        "emoji": info["emoji"],
    }

# --- Board UI ---
size = st.session_state.size
for r in range(size):
    cols = st.columns(size, gap="small")
    for c in range(size):
        label = square_label(r, c)
        is_selected = (st.session_state.selected == (r, c))
        btn_text = f"[{label}]" if is_selected else f" {label} "
        if cols[c].button(btn_text, key=f"sq_{r}_{c}", use_container_width=True):
            st.session_state.selected = (r, c)

# --- Cards area (only after selecting a square) ---
if st.session_state.selected is not None:
    team = st.session_state.turn
    team_cls = "red" if team == "Red" else "blue"
    r, c = st.session_state.selected

    st.write("### Choose a card")
    st.caption(f"Selected square: row {r+1}, col {c+1}  •  Current turn: {team}")

    unit_cols = st.columns(4, gap="small")

    cards = [
        ("Miner",  "Place a Mine (⛏️)"),
        ("Melee",  "Place a Melee Barracks (⚔️)"),
        ("Archer", "Place an Archer Barracks (🏹)"),
        ("Tower",  "Place a Tower (🗼)"),
    ]

    for i, (name, desc) in enumerate(cards):
        with unit_cols[i]:
            st.markdown(
                f"""
                <div class="unit-card {team_cls}">
                  <p class="unit-title">{name}</p>
                  <div class="unit-sub">{desc}</div>
                  <div class="tiny">Team: {team}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Clicking this "card button" places the structure
            if st.button(f"Place {name}", key=f"place_{name}", use_container_width=True):
                place_structure(name)

    # Show what's currently on the selected square
    placed = st.session_state.placements.get((r, c))
    if placed:
        st.success(f"This square now has **{placed['type']}** {placed['emoji']} for **{placed['team']}**.")

# --- Footer ---
st.write("---")
if st.session_state.selected is None:
    st.write("Selected: *(none)*")
else:
    r, c = st.session_state.selected
    st.write(f"Selected: row {r+1}, col {c+1}")