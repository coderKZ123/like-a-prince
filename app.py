import random
import streamlit as st

st.set_page_config(page_title="War Game (General)", layout="centered")

# =========================================================
# GENERAL GAME CONFIG (edit this to add new cards/units)
# =========================================================
BOARD_SIZE = 7

# Cards you can place in BUILD phase (structures)
# Each card places a STRUCTURE on the board.
CARD_DEFS = {
    "Melee Barracks":  {"type": "Barracks", "spawns": "Melee",  "emoji": "⚔️"},
    "Archer Barracks": {"type": "Barracks", "spawns": "Archer", "emoji": "🏹"},
    "Tower":           {"type": "Tower",    "spawns": None,     "emoji": "🗼"},
}

# Units (things that fight). Troops are spawned from barracks.
# - move_pattern: list of steps to move each turn, cycling by turn count. (e.g., [1,1,2] means "2 squares every 3rd move")
# - range: Manhattan range (no diagonals)
# - hp: hits it can take before dying
# - stationary: if True, never moves (good for towers if you ever want "tower unit" style)
UNIT_DEFS = {
    "Melee":  {"emoji": "🗡️", "hp": 2, "range": 1, "move_pattern": [1, 1, 2], "respawn_new_path": True},
    "Archer": {"emoji": "🏹", "hp": 2, "range": 2, "move_pattern": [1],       "respawn_new_path": True},
}

# Structures that can attack and/or have hp (right now Tower only)
STRUCTURE_COMBAT = {
    "Tower": {"hp": 3, "range": 3, "attacks": True},
    "Castle": {"hp": 10, "range": 0, "attacks": False},  # optional future use
}

PATH_EMOJI = "▫️"


# =========================================================
# Session State
# =========================================================
if "size" not in st.session_state:
    st.session_state.size = BOARD_SIZE
if "selected" not in st.session_state:
    st.session_state.selected = None
if "turn" not in st.session_state:
    st.session_state.turn = "Red"
if "phase" not in st.session_state:
    st.session_state.phase = "build"  # build -> play

if "placements" not in st.session_state:
    # {(r,c): {"team": "Red", "type": "Tower"/"Barracks"/"Castle", "emoji":"🗼", "spawns":"Melee"/None}}
    st.session_state.placements = {}

if "structure_hp" not in st.session_state:
    # {(r,c): hp_remaining} for structures that have hp (towers now)
    st.session_state.structure_hp = {}

if "troops" not in st.session_state:
    # troop:
    # {
    #   "id": int, "team": "Red"/"Blue",
    #   "unit": "Melee"/"Archer",
    #   "spawn": (r,c),
    #   "path": [(r,c),...], "idx": int,
    #   "hp": int,          # remaining hp
    #   "turns": int        # how many Next Move presses this troop experienced
    # }
    st.session_state.troops = []

if "next_id" not in st.session_state:
    st.session_state.next_id = 1

if "paths" not in st.session_state:
    st.session_state.paths = {"Red": set(), "Blue": set()}


# =========================================================
# Helpers
# =========================================================
def enemy(team: str) -> str:
    return "Blue" if team == "Red" else "Red"

def in_bounds(r, c) -> bool:
    size = st.session_state.size
    return 0 <= r < size and 0 <= c < size

def neighbors4(r, c):
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc):
            yield rr, cc

def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def get_castle_pos(team: str):
    size = st.session_state.size
    mid = size // 2
    return (mid, 0) if team == "Red" else (mid, size - 1)

def init_castles():
    size = st.session_state.size
    mid = size // 2

    st.session_state.placements[(mid, 0)] = {"team": "Red", "type": "Castle", "emoji": "🏰", "spawns": None}
    st.session_state.placements[(mid, size - 1)] = {"team": "Blue", "type": "Castle", "emoji": "🏰", "spawns": None}

def reset():
    st.session_state.selected = None
    st.session_state.turn = "Red"
    st.session_state.phase = "build"
    st.session_state.placements = {}
    st.session_state.structure_hp = {}
    st.session_state.troops = []
    st.session_state.paths = {"Red": set(), "Blue": set()}
    st.session_state.next_id = 1
    init_castles()

def troop_pos(t):
    return t["path"][t["idx"]]

def troop_positions_map():
    mp = {}
    for t in st.session_state.troops:
        mp.setdefault(troop_pos(t), []).append(t)
    return mp

def all_structures():
    # yields ((r,c), data)
    for pos, data in st.session_state.placements.items():
        yield pos, data

def structure_has_hp(stype: str) -> bool:
    return stype in STRUCTURE_COMBAT and STRUCTURE_COMBAT[stype].get("hp", 0) > 0

def structure_can_attack(stype: str) -> bool:
    return stype in STRUCTURE_COMBAT and STRUCTURE_COMBAT[stype].get("attacks", False)

def structure_range(stype: str) -> int:
    return STRUCTURE_COMBAT.get(stype, {}).get("range", 0)

def rebuild_paths_sets():
    # show path markers for all troop paths
    paths = {"Red": set(), "Blue": set()}
    for t in st.session_state.troops:
        for sq in t["path"][1:-1]:
            paths[t["team"]].add(sq)
    st.session_state.paths = paths


# =========================================================
# Random ANY path (DFS backtracking)
# =========================================================
def random_any_path(start, goal, blocked_set, max_steps=15000):
    stack = [(start, [start])]
    visited = set([start])

    steps = 0
    while stack and steps < max_steps:
        steps += 1
        cur, path = stack[-1]

        if cur == goal:
            return path

        nbrs = list(neighbors4(cur[0], cur[1]))
        random.shuffle(nbrs)

        moved = False
        for nxt in nbrs:
            if nxt in blocked_set:
                continue
            if nxt in visited:
                continue
            visited.add(nxt)
            stack.append((nxt, path + [nxt]))
            moved = True
            break

        if not moved:
            stack.pop()

    return None

def build_blocked_set(start, goal):
    # block all structures except start and goal
    blocked = set()
    for pos in st.session_state.placements.keys():
        if pos == start:
            continue
        if pos == goal:
            continue
        blocked.add(pos)
    return blocked

def new_path_for_spawn(team: str, spawn_pos, old_path=None, attempts=30):
    goal = get_castle_pos(enemy(team))
    blocked = build_blocked_set(spawn_pos, goal)

    for _ in range(attempts):
        p = random_any_path(spawn_pos, goal, blocked_set=blocked)
        if not p:
            continue
        if old_path is None or p != old_path:
            return p
    return old_path  # fallback


# =========================================================
# Build -> spawn troops (one per barracks)
# =========================================================
def find_barracks(team: str):
    for pos, data in st.session_state.placements.items():
        if data["team"] == team and data["type"] == "Barracks":
            yield pos, data

def spawn_troop(team: str, unit_name: str, spawn_pos, path):
    u = UNIT_DEFS[unit_name]
    troop = {
        "id": st.session_state.next_id,
        "team": team,
        "unit": unit_name,
        "spawn": spawn_pos,
        "path": path,
        "idx": 0,
        "hp": u["hp"],
        "turns": 0,
    }
    st.session_state.next_id += 1
    st.session_state.troops.append(troop)

def compute_paths_and_spawn_all():
    st.session_state.troops = []
    for team in ["Red", "Blue"]:
        for spawn_pos, bdata in find_barracks(team):
            unit_name = bdata.get("spawns")
            if not unit_name:
                continue
            if unit_name not in UNIT_DEFS:
                continue

            path = new_path_for_spawn(team, spawn_pos, old_path=None)
            if not path:
                continue
            spawn_troop(team, unit_name, spawn_pos, path)

    rebuild_paths_sets()


# =========================================================
# Movement
# =========================================================
def steps_this_turn(troop) -> int:
    unit = UNIT_DEFS[troop["unit"]]
    pattern = unit["move_pattern"]
    # troop["turns"] counts from 1.. so we compute after incrementing
    idx = (troop["turns"] - 1) % len(pattern)
    return pattern[idx]

def move_troops():
    for t in st.session_state.troops:
        t["turns"] += 1
        steps = steps_this_turn(t)
        t["idx"] = min(t["idx"] + steps, len(t["path"]) - 1)


# =========================================================
# Combat (AUTO once after each move)
# Everyone attacks ONCE per Next Move.
# =========================================================
def apply_damage_simultaneous(troop_dmg, struct_dmg):
    # Apply troop damage (reduce hp)
    for t in st.session_state.troops:
        t["hp"] -= troop_dmg.get(t["id"], 0)

    # Apply structure damage (reduce hp)
    for pos, dmg in struct_dmg.items():
        if pos not in st.session_state.structure_hp:
            # safety: initialize if missing
            stype = st.session_state.placements.get(pos, {}).get("type")
            if stype and structure_has_hp(stype):
                st.session_state.structure_hp[pos] = STRUCTURE_COMBAT[stype]["hp"]
        if pos in st.session_state.structure_hp:
            st.session_state.structure_hp[pos] -= dmg

def cleanup_deaths_and_respawns():
    # Respawn troops that died
    for t in st.session_state.troops:
        if t["hp"] <= 0:
            unit = UNIT_DEFS[t["unit"]]
            t["hp"] = unit["hp"]
            t["idx"] = 0
            t["turns"] = 0
            if unit.get("respawn_new_path", False):
                t["path"] = new_path_for_spawn(t["team"], t["spawn"], old_path=t["path"], attempts=40)

    # Remove dead structures (towers)
    dead = [pos for pos, hp in st.session_state.structure_hp.items() if hp <= 0]
    for pos in dead:
        data = st.session_state.placements.get(pos)
        if data and data["type"] == "Tower":
            del st.session_state.placements[pos]
        del st.session_state.structure_hp[pos]

def pick_one_target(valid_targets):
    return random.choice(valid_targets) if valid_targets else None

def auto_attack_once():
    """
    Targets allowed:
      - Troops can attack enemy troops and enemy damageable structures (towers) within unit range.
      - Towers (and any attacking structures) can attack enemy troops and enemy towers within their range.
    No diagonals -> Manhattan distance.
    """
    troops = list(st.session_state.troops)
    structures = list(all_structures())

    troop_dmg = {t["id"]: 0 for t in troops}
    struct_dmg = {}  # pos -> dmg

    # --- Troops attack once ---
    for atk in troops:
        rng = UNIT_DEFS[atk["unit"]]["range"]
        a_pos = troop_pos(atk)

        valid = []

        # enemy troops
        for tgt in troops:
            if tgt["team"] == atk["team"]:
                continue
            d = manhattan(a_pos, troop_pos(tgt))
            if 0 < d <= rng:
                valid.append(("troop", tgt["id"]))

        # enemy structures with hp (towers)
        for spos, sdata in structures:
            if sdata["team"] == atk["team"]:
                continue
            if not structure_has_hp(sdata["type"]):
                continue
            d = manhattan(a_pos, spos)
            if 0 < d <= rng:
                valid.append(("structure", spos))

        target = pick_one_target(valid)
        if target:
            kind, ref = target
            if kind == "troop":
                troop_dmg[ref] += 1
            else:
                struct_dmg[ref] = struct_dmg.get(ref, 0) + 1

    # --- Structures attack once (towers) ---
    for spos, sdata in structures:
        stype = sdata["type"]
        if not structure_can_attack(stype):
            continue
        rng = structure_range(stype)

        valid = []
        # enemy troops
        for tgt in troops:
            if tgt["team"] == sdata["team"]:
                continue
            d = manhattan(spos, troop_pos(tgt))
            if 0 < d <= rng:
                valid.append(("troop", tgt["id"]))

        # enemy structures with hp
        for epos, edata in structures:
            if edata["team"] == sdata["team"]:
                continue
            if not structure_has_hp(edata["type"]):
                continue
            d = manhattan(spos, epos)
            if 0 < d <= rng:
                valid.append(("structure", epos))

        target = pick_one_target(valid)
        if target:
            kind, ref = target
            if kind == "troop":
                troop_dmg[ref] += 1
            else:
                struct_dmg[ref] = struct_dmg.get(ref, 0) + 1

    apply_damage_simultaneous(troop_dmg, struct_dmg)
    cleanup_deaths_and_respawns()
    rebuild_paths_sets()


def next_move():
    move_troops()
    auto_attack_once()


# =========================================================
# Init castles on first run
# =========================================================
if len(st.session_state.placements) == 0:
    init_castles()


# =========================================================
# UI
# =========================================================
st.markdown(
    """
    <style>
      .unit-card {
        border-radius: 14px;
        padding: 12px 12px;
        border: 2px solid rgba(0,0,0,0.12);
        margin: 0;
      }
      .unit-title { font-size: 16px; font-weight: 800; margin: 0; }
      .unit-sub { font-size: 12px; opacity: 0.85; margin-top: 6px; }
      .red { background: rgba(255, 0, 0, 0.10); border-color: rgba(255, 0, 0, 0.35); }
      .blue { background: rgba(0, 120, 255, 0.10); border-color: rgba(0, 120, 255, 0.35); }
      .tiny { font-size: 11px; opacity: 0.8; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("War Game (General Version)")
st.caption("BUILD: place structures. PLAY: press Next Move → troops move → everyone attacks once automatically.")

with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Reset"):
        reset()

    st.divider()
    st.write("Phase:")
    st.subheader("BUILD" if st.session_state.phase == "build" else "PLAY")

    st.divider()
    if st.session_state.phase == "build":
        if st.button("▶️ Play (spawn troops)"):
            st.session_state.phase = "play"
            st.session_state.selected = None
            compute_paths_and_spawn_all()
    else:
        if st.button("➡️ Next Move (move + auto attack)"):
            next_move()

    st.divider()
    st.write("Placing for:")
    st.subheader(st.session_state.turn)
    if st.session_state.phase == "build":
        if st.button("🔁 Switch Player"):
            st.session_state.turn = enemy(st.session_state.turn)

st.write("### Board")
if st.session_state.phase == "build":
    st.info("Click a square → place a Barracks/Tower. Castles are already placed.")
else:
    st.info("Press **Next Move**: troops move, then troops + towers attack once (no diagonals).")

def square_label(r, c):
    mp = troop_positions_map()
    pos = (r, c)

    # Troops (show team + unit emoji + HP)
    if pos in mp:
        troops_here = mp[pos]
        teams = {t["team"] for t in troops_here}
        if len(teams) > 1:
            return "💥"
        t0 = troops_here[0]
        u = UNIT_DEFS[t0["unit"]]
        team_initial = "R" if t0["team"] == "Red" else "B"
        return f"{team_initial}{u['emoji']}{t0['hp']}"

    # Structures (show team + emoji + HP if applicable)
    s = st.session_state.placements.get(pos)
    if s:
        team_initial = "R" if s["team"] == "Red" else "B"
        if structure_has_hp(s["type"]):
            hp = st.session_state.structure_hp.get(pos, STRUCTURE_COMBAT[s["type"]]["hp"])
            return f"{team_initial}{s['emoji']}{hp}"
        return f"{team_initial}{s['emoji']}"

    # Path markers (play phase)
    if st.session_state.phase == "play":
        if pos in st.session_state.paths["Red"] or pos in st.session_state.paths["Blue"]:
            return PATH_EMOJI

    return "·"

def place_card(card_name: str):
    if st.session_state.phase != "build":
        return
    if st.session_state.selected is None:
        return
    r, c = st.session_state.selected
    pos = (r, c)

    # Can't overwrite anything (including castles)
    if pos in st.session_state.placements:
        st.warning("That square is occupied.")
        return

    card = CARD_DEFS[card_name]
    st.session_state.placements[pos] = {
        "team": st.session_state.turn,
        "type": card["type"],
        "emoji": card["emoji"],
        "spawns": card.get("spawns"),
    }

    # Initialize hp for damageable structures (tower)
    if structure_has_hp(card["type"]):
        st.session_state.structure_hp[pos] = STRUCTURE_COMBAT[card["type"]]["hp"]

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

# Cards area
if st.session_state.phase == "build" and st.session_state.selected is not None:
    team = st.session_state.turn
    team_cls = "red" if team == "Red" else "blue"
    r, c = st.session_state.selected

    st.write("### Place a card")
    st.caption(f"Selected square: row {r+1}, col {c+1} • Team: {team}")

    card_cols = st.columns(len(CARD_DEFS), gap="small")
    for i, (name, info) in enumerate(CARD_DEFS.items()):
        with card_cols[i]:
            desc = ""
            if info["type"] == "Barracks":
                desc = f"Spawns: {info['spawns']}"
            elif info["type"] == "Tower":
                desc = f"Range {STRUCTURE_COMBAT['Tower']['range']} • HP {STRUCTURE_COMBAT['Tower']['hp']}"
            st.markdown(
                f"""
                <div class="unit-card {team_cls}">
                  <p class="unit-title">{name}</p>
                  <div class="unit-sub">{desc}</div>
                  <div class="tiny">Places: {info['emoji']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Place {name}", key=f"place_{name}", use_container_width=True):
                place_card(name)

st.write("---")
st.write("### How to customize this general version")
st.write("- Add a new **unit**: edit `UNIT_DEFS` (emoji, hp, range, move_pattern).")
st.write("- Add a new **card**: edit `CARD_DEFS` (type, emoji, and `spawns` if it’s a barracks).")
st.write("- Add structure combat rules: edit `STRUCTURE_COMBAT` (hp, range, attacks).")