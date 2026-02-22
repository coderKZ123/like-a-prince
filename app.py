import random
from collections import deque
import streamlit as st

st.set_page_config(page_title="War Game", layout="centered")

# =========================
# Session state
# =========================
if "size" not in st.session_state:
    st.session_state.size = 7
if "selected" not in st.session_state:
    st.session_state.selected = None
if "turn" not in st.session_state:
    st.session_state.turn = "Red"
if "placements" not in st.session_state:
    st.session_state.placements = {}
if "phase" not in st.session_state:
    # "build" -> place barracks, then "play" -> show path + move troops
    st.session_state.phase = "build"
if "paths" not in st.session_state:
    # {"Red": set((r,c),...), "Blue": set(...)} squares on path (excluding castles)
    st.session_state.paths = {"Red": set(), "Blue": set()}
if "troops" not in st.session_state:
    # list of troops:
    # {"id": int, "team": "Red"/"Blue", "path": [(r,c),...], "idx": int}
    st.session_state.troops = []
if "next_id" not in st.session_state:
    st.session_state.next_id = 1


# =========================
# Constants
# =========================
CARD_TO_STRUCTURE = {
    "Miner":  {"type": "Mine",            "emoji": "⛏️"},
    "Melee":  {"type": "Melee Barracks",  "emoji": "⚔️"},
    "Archer": {"type": "Archer Barracks", "emoji": "🏹"},
    "Tower":  {"type": "Tower",           "emoji": "🗼"},
}
TROOP_EMOJI = "🗡️"
PATH_EMOJI = "▫️"  # shown on path squares

# =========================
# Helpers
# =========================
def enemy(team: str) -> str:
    return "Blue" if team == "Red" else "Red"

def in_bounds(r, c) -> bool:
    size = st.session_state.size
    return 0 <= r < size and 0 <= c < size

def neighbors4(r, c):
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:  # no diagonal
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc):
            yield rr, cc

def get_castle_pos(team: str):
    size = st.session_state.size
    mid = size // 2
    if team == "Red":
        return (mid, 0)
    return (mid, size - 1)

def init_castles():
    size = st.session_state.size
    mid = size // 2
    st.session_state.placements[(mid, 0)] = {"team": "Red", "type": "Castle", "emoji": "🏰"}
    st.session_state.placements[(mid, size - 1)] = {"team": "Blue", "type": "Castle", "emoji": "🏰"}

def reset():
    st.session_state.selected = None
    st.session_state.turn = "Red"
    st.session_state.placements = {}
    st.session_state.phase = "build"
    st.session_state.paths = {"Red": set(), "Blue": set()}
    st.session_state.troops = []
    st.session_state.next_id = 1
    init_castles()

def is_castle_square(r, c) -> bool:
    data = st.session_state.placements.get((r,c))
    return bool(data and data["type"] == "Castle")

def is_blocked_for_path(r, c) -> bool:
    """
    Path cannot go through buildings/units, but CAN start on a barracks square.
    Also cannot go onto castles (goal is the castle square, but we keep path squares excluding castle for display).
    """
    if is_castle_square(r, c):
        return True
    data = st.session_state.placements.get((r,c))
    if not data:
        return False
    # blocked if any structure; barracks square is handled separately in BFS start
    return True

def find_positions_by(team: str, type_name: str):
    for (r,c), data in st.session_state.placements.items():
        if data["team"] == team and data["type"] == type_name:
            yield (r,c)

def random_shortest_path(start, goal, blocked_set):
    """
    BFS shortest path, but randomize neighbor order so the chosen shortest path is random.
    Returns list of (r,c) including start and goal, or None if no path.
    """
    q = deque([start])
    parent = {start: None}

    while q:
        cur = q.popleft()
        if cur == goal:
            break
        nbrs = list(neighbors4(cur[0], cur[1]))
        random.shuffle(nbrs)
        for nxt in nbrs:
            if nxt in parent:
                continue
            if nxt in blocked_set:
                continue
            parent[nxt] = cur
            q.append(nxt)

    if goal not in parent:
        return None

    # reconstruct
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path

def compute_paths_and_spawn_troops():
    """
    For each team's Melee Barracks:
      - compute a random (shortest) no-diagonal path to enemy castle
      - store path squares for display
      - create 1 troop that will walk along that path
    """
    st.session_state.paths = {"Red": set(), "Blue": set()}
    st.session_state.troops = []

    # blocked squares: any placed structure except the barracks start squares
    all_structures = set(st.session_state.placements.keys())

    for team in ["Red", "Blue"]:
        goal = get_castle_pos(enemy(team))  # opponent castle square
        for start in find_positions_by(team, "Melee Barracks"):
            # Build blocked set for BFS:
            # - block all structures
            # - BUT allow the start square
            # - block castles (handled by is_blocked_for_path, but simpler to explicitly manage)
            blocked = set()
            for pos in all_structures:
                if pos == start:
                    continue
                # allow stepping onto goal (castle) ONLY as final node in BFS
                if pos == goal:
                    continue
                blocked.add(pos)

            path = random_shortest_path(start, goal, blocked)
            if not path:
                continue

            # Save squares (exclude start and goal from path markers, optional)
            for sq in path[1:-1]:
                st.session_state.paths[team].add(sq)

            troop = {
                "id": st.session_state.next_id,
                "team": team,
                "path": path,  # includes start..goal
                "idx": 0,      # troop is currently at path[idx]
            }
            st.session_state.next_id += 1
            st.session_state.troops.append(troop)

def step_troops_one_square():
    """
    Each troop moves 1 square along its stored path (no diagonal by construction).
    """
    for troop in st.session_state.troops:
        if troop["idx"] < len(troop["path"]) - 1:
            troop["idx"] += 1

def troop_positions_map():
    """
    Return dict {(r,c): [troop,...]} (can be multiple troops on same square).
    We'll display just one emoji even if stacked.
    """
    mp = {}
    for t in st.session_state.troops:
        r, c = t["path"][t["idx"]]
        mp.setdefault((r,c), []).append(t)
    return mp

# Ensure castles exist (first run)
if len(st.session_state.placements) == 0:
    init_castles()

# =========================
# CSS
# =========================
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

# =========================
# Header
# =========================
st.title("War Game (Paths to Castle)")
st.caption("Build phase: place Melee Barracks. Then press Play: computer draws random (no-diagonal) paths to the enemy castle and shows troops walking.")

# =========================
# Sidebar controls
# =========================
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Reset"):
        reset()

    st.divider()
    st.write("Phase:")
    st.subheader("BUILD" if st.session_state.phase == "build" else "PLAY")

    st.divider()
    if st.session_state.phase == "build":
        if st.button("▶️ Play (compute paths)"):
            st.session_state.phase = "play"
            st.session_state.selected = None
            compute_paths_and_spawn_troops()
    else:
        if st.button("➡️ Next Step (move troops 1 square)"):
            step_troops_one_square()

    st.divider()
    st.write("Turn (for placing):")
    st.subheader(st.session_state.turn)
    if st.session_state.phase == "build":
        if st.button("🔁 Switch Player"):
            st.session_state.turn = enemy(st.session_state.turn)

# =========================
# Board helpers (display)
# =========================
def square_label(r, c):
    """
    Layering:
    1) troop (🗡️)
    2) building (castle/barracks/etc.)
    3) path marker (▫️)
    4) empty dot
    """
    tmap = troop_positions_map()
    if (r,c) in tmap:
        team_initial = "R" if tmap[(r,c)][0]["team"] == "Red" else "B"
        return f"{team_initial}{TROOP_EMOJI}"

    data = st.session_state.placements.get((r, c))
    if data:
        team_initial = "R" if data["team"] == "Red" else "B"
        return f"{team_initial}{data['emoji']}"

    if st.session_state.phase == "play":
        # show either team's path squares
        if (r,c) in st.session_state.paths["Red"] or (r,c) in st.session_state.paths["Blue"]:
            return PATH_EMOJI

    return "·"

def place_structure(card_name: str):
    if st.session_state.phase != "build":
        return
    if st.session_state.selected is None:
        return
    r, c = st.session_state.selected

    # can't overwrite castles or any existing structure
    existing = st.session_state.placements.get((r,c))
    if existing:
        st.warning("That square is occupied.")
        return

    info = CARD_TO_STRUCTURE[card_name]
    st.session_state.placements[(r,c)] = {
        "team": st.session_state.turn,
        "type": info["type"],
        "emoji": info["emoji"],
    }

# =========================
# Board UI
# =========================
st.write("### Board")
if st.session_state.phase == "build":
    st.info("BUILD: Place **Melee Barracks (⚔️)** for both players. Then press **Play** in the sidebar.")
else:
    st.info("PLAY: Paths (▫️) are shown. Press **Next Step** to move troops (🗡️) one square (no diagonals).")

size = st.session_state.size
disable_click = (st.session_state.phase != "build")

for r in range(size):
    cols = st.columns(size, gap="small")
    for c in range(size):
        label = square_label(r, c)
        is_selected = (st.session_state.selected == (r, c))
        btn_text = f"[{label}]" if is_selected else f" {label} "
        if cols[c].button(btn_text, key=f"sq_{r}_{c}", use_container_width=True, disabled=disable_click):
            st.session_state.selected = (r, c)

# =========================
# Cards (only build phase)
# =========================
if st.session_state.phase == "build" and st.session_state.selected is not None:
    team = st.session_state.turn
    team_cls = "red" if team == "Red" else "blue"
    r, c = st.session_state.selected

    st.write("### Choose a card")
    st.caption(f"Selected square: row {r+1}, col {c+1}  •  Placing for: {team}")

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
            if st.button(f"Place {name}", key=f"place_{name}", use_container_width=True):
                place_structure(name)

# =========================
# Debug / info (nice for kids)
# =========================
st.write("---")
if st.session_state.phase == "play":
    st.write("### Paths & Troops")
    if len(st.session_state.troops) == 0:
        st.warning("No paths found. Try placing Melee Barracks with a clear route to the enemy castle (avoid blocking the board).")
    else:
        for t in st.session_state.troops:
            cur = t["path"][t["idx"]]
            goal = t["path"][-1]
            st.write(f"Troop #{t['id']} ({t['team']}) at {cur} → castle at {goal} | step {t['idx']}/{len(t['path'])-1}")

if st.session_state.selected is None:
    st.write("Selected: *(none)*")
else:
    r, c = st.session_state.selected
    st.write(f"Selected: row {r+1}, col {c+1}")