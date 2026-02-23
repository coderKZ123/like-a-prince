# app.py  (ready to deploy)
import random
import streamlit as st

st.set_page_config(page_title="War Game (Deployable)", layout="centered")

# =========================================================
# CONFIG (easy to extend)
# =========================================================
BOARD_SIZE = 7
TEAM_A, TEAM_B = "Red", "Blue"
TEAMS = [TEAM_A, TEAM_B]
PATH_EMOJI = "▫️"

# Structures you can place (BUILD)
CARD_DEFS = {
    "Melee Barracks":  {"type": "Barracks", "spawns": "Melee",  "emoji": "⚔️"},
    "Archer Barracks": {"type": "Barracks", "spawns": "Archer", "emoji": "🏹"},
    "Tower":           {"type": "Tower",    "spawns": None,     "emoji": "🗼"},
}

# Units spawned from barracks
UNIT_DEFS = {
    # move_pattern repeats by turns: [1,1,2] => 2 squares every 3rd move
    "Melee":  {"emoji": "🗡️", "hp": 2, "range": 1, "move_pattern": [1, 1, 2], "respawn_new_path": True},
    "Archer": {"emoji": "🏹", "hp": 2, "range": 2, "move_pattern": [1],       "respawn_new_path": True},
}

# Structures with HP and/or attacks
STRUCTURE_COMBAT = {
    "Barracks": {"hp": 4, "range": 0, "attacks": False},
    "Tower":    {"hp": 3, "range": 3, "attacks": True},
    "Castle":   {"hp": 10, "range": 0, "attacks": False},
}


# =========================================================
# Session State Init
# =========================================================
def ss_init():
    if "size" not in st.session_state:
        st.session_state.size = BOARD_SIZE
    if "phase" not in st.session_state:
        st.session_state.phase = "build"  # build | play
    if "turn" not in st.session_state:
        st.session_state.turn = TEAM_A
    if "selected" not in st.session_state:
        st.session_state.selected = None

    if "placements" not in st.session_state:
        # {(r,c): {"team":..., "type":..., "emoji":..., "spawns":...}}
        st.session_state.placements = {}
    if "structure_hp" not in st.session_state:
        # {(r,c): hp}
        st.session_state.structure_hp = {}
    if "troops" not in st.session_state:
        # troop:
        # {"id": int, "team":..., "unit":..., "spawn": (r,c),
        #  "path": [(r,c)...], "idx": int, "hp": int, "turns": int}
        st.session_state.troops = []
    if "paths" not in st.session_state:
        st.session_state.paths = {TEAM_A: set(), TEAM_B: set()}
    if "next_id" not in st.session_state:
        st.session_state.next_id = 1


# =========================================================
# Helpers
# =========================================================
def enemy(team: str) -> str:
    return TEAM_B if team == TEAM_A else TEAM_A

def in_bounds(r, c) -> bool:
    n = st.session_state.size
    return 0 <= r < n and 0 <= c < n

def neighbors4(r, c):
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        rr, cc = r + dr, c + dc
        if in_bounds(rr, cc):
            yield rr, cc

def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def get_castle_pos(team: str):
    n = st.session_state.size
    mid = n // 2
    return (mid, 0) if team == TEAM_A else (mid, n - 1)

def structure_has_hp(stype: str) -> bool:
    return stype in STRUCTURE_COMBAT and STRUCTURE_COMBAT[stype].get("hp", 0) > 0

def structure_can_attack(stype: str) -> bool:
    return stype in STRUCTURE_COMBAT and STRUCTURE_COMBAT[stype].get("attacks", False)

def structure_range(stype: str) -> int:
    return STRUCTURE_COMBAT.get(stype, {}).get("range", 0)

def troop_pos(t):
    return t["path"][t["idx"]]

def troop_positions_map():
    mp = {}
    for t in st.session_state.troops:
        mp.setdefault(troop_pos(t), []).append(t)
    return mp

def all_structures():
    for pos, data in st.session_state.placements.items():
        yield pos, data

def rebuild_paths_sets():
    paths = {TEAM_A: set(), TEAM_B: set()}
    for t in st.session_state.troops:
        for sq in t["path"][1:-1]:
            paths[t["team"]].add(sq)
    st.session_state.paths = paths


# =========================================================
# Reset + Castles
# =========================================================
def init_castles():
    n = st.session_state.size
    mid = n // 2
    left, right = (mid, 0), (mid, n - 1)

    st.session_state.placements[left] = {"team": TEAM_A, "type": "Castle", "emoji": "🏰", "spawns": None}
    st.session_state.placements[right] = {"team": TEAM_B, "type": "Castle", "emoji": "🏰", "spawns": None}

    st.session_state.structure_hp[left] = STRUCTURE_COMBAT["Castle"]["hp"]
    st.session_state.structure_hp[right] = STRUCTURE_COMBAT["Castle"]["hp"]

def reset_game():
    st.session_state.phase = "build"
    st.session_state.turn = TEAM_A
    st.session_state.selected = None
    st.session_state.placements = {}
    st.session_state.structure_hp = {}
    st.session_state.troops = []
    st.session_state.paths = {TEAM_A: set(), TEAM_B: set()}
    st.session_state.next_id = 1
    init_castles()


# =========================================================
# Pathfinding (ANY path, no diagonals)
# =========================================================
def random_any_path(start, goal, blocked_set, max_steps=20000):
    stack = [(start, [start])]
    visited = {start}
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
            if nxt in blocked_set or nxt in visited:
                continue
            visited.add(nxt)
            stack.append((nxt, path + [nxt]))
            moved = True
            break

        if not moved:
            stack.pop()

    return None

def build_blocked_set(start, goal):
    blocked = set()
    for pos in st.session_state.placements.keys():
        if pos == start or pos == goal:
            continue
        blocked.add(pos)
    return blocked

def new_path_for_spawn(team: str, spawn_pos, old_path=None, attempts=60):
    goal = get_castle_pos(enemy(team))
    blocked = build_blocked_set(spawn_pos, goal)

    for _ in range(attempts):
        p = random_any_path(spawn_pos, goal, blocked_set=blocked)
        if not p:
            continue
        if old_path is None or p != old_path:
            return p
    return old_path


# =========================================================
# Troops (spawn 1 per barracks)
# =========================================================
def find_barracks(team: str):
    for pos, data in st.session_state.placements.items():
        if data["team"] == team and data["type"] == "Barracks":
            yield pos, data

def spawn_troop(team: str, unit_name: str, spawn_pos, path):
    u = UNIT_DEFS[unit_name]
    t = {
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
    st.session_state.troops.append(t)

def start_play():
    st.session_state.troops = []

    for team in TEAMS:
        for spawn_pos, bdata in find_barracks(team):
            unit_name = bdata.get("spawns")
            if not unit_name or unit_name not in UNIT_DEFS:
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
    pattern = UNIT_DEFS[troop["unit"]]["move_pattern"]
    idx = (troop["turns"] - 1) % len(pattern)
    return pattern[idx]

def move_troops():
    for t in st.session_state.troops:
        t["turns"] += 1
        steps = steps_this_turn(t)
        t["idx"] = min(t["idx"] + steps, len(t["path"]) - 1)


# =========================================================
# Combat (auto after each move)
# =========================================================
def pick_one(valid):
    return random.choice(valid) if valid else None

def apply_damage_simultaneous(troop_dmg, struct_dmg):
    for t in st.session_state.troops:
        t["hp"] -= troop_dmg.get(t["id"], 0)

    for pos, dmg in struct_dmg.items():
        if pos not in st.session_state.structure_hp:
            stype = st.session_state.placements.get(pos, {}).get("type")
            if stype and structure_has_hp(stype):
                st.session_state.structure_hp[pos] = STRUCTURE_COMBAT[stype]["hp"]
        if pos in st.session_state.structure_hp:
            st.session_state.structure_hp[pos] -= dmg

def cleanup_deaths_and_respawns():
    # troop respawn
    for t in st.session_state.troops:
        if t["hp"] <= 0:
            u = UNIT_DEFS[t["unit"]]
            t["hp"] = u["hp"]
            t["idx"] = 0
            t["turns"] = 0
            if u.get("respawn_new_path", False):
                t["path"] = new_path_for_spawn(t["team"], t["spawn"], old_path=t["path"], attempts=80)

    # remove destroyed structures (towers/barracks/castles)
    dead = [pos for pos, hp in st.session_state.structure_hp.items() if hp <= 0]
    for pos in dead:
        if pos in st.session_state.placements:
            del st.session_state.placements[pos]
        del st.session_state.structure_hp[pos]

def auto_attack_once():
    troops = list(st.session_state.troops)
    structures = list(all_structures())

    troop_dmg = {t["id"]: 0 for t in troops}
    struct_dmg = {}

    # ---- Troops attack once ----
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

        # enemy structures with HP (tower/barracks/castle)
        for spos, sdata in structures:
            if sdata["team"] == atk["team"]:
                continue
            if not structure_has_hp(sdata["type"]):
                continue
            d = manhattan(a_pos, spos)
            if 0 < d <= rng:
                valid.append(("structure", spos))

        target = pick_one(valid)
        if target:
            kind, ref = target
            if kind == "troop":
                troop_dmg[ref] += 1
            else:
                struct_dmg[ref] = struct_dmg.get(ref, 0) + 1

    # ---- Attack-capable structures (towers) ----
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

        # enemy structures with HP
        for epos, edata in structures:
            if edata["team"] == sdata["team"]:
                continue
            if not structure_has_hp(edata["type"]):
                continue
            d = manhattan(spos, epos)
            if 0 < d <= rng:
                valid.append(("structure", epos))

        target = pick_one(valid)
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
# Win condition
# =========================================================
def check_winner():
    a = get_castle_pos(TEAM_A)
    b = get_castle_pos(TEAM_B)
    a_hp = st.session_state.structure_hp.get(a, 0)
    b_hp = st.session_state.structure_hp.get(b, 0)
    if a_hp <= 0:
        return TEAM_B
    if b_hp <= 0:
        return TEAM_A
    return None


# =========================================================
# Render helpers
# =========================================================
def square_label(r, c):
    pos = (r, c)
    mp = troop_positions_map()

    # troops (team initial + unit emoji + hp)
    if pos in mp:
        troops_here = mp[pos]
        teams_here = {t["team"] for t in troops_here}
        if len(teams_here) > 1:
            return "💥"
        t0 = troops_here[0]
        team_initial = "R" if t0["team"] == TEAM_A else "B"
        u = UNIT_DEFS[t0["unit"]]
        return f"{team_initial}{u['emoji']}{t0['hp']}"

    # structures (team initial + emoji + hp if has hp)
    s = st.session_state.placements.get(pos)
    if s:
        team_initial = "R" if s["team"] == TEAM_A else "B"
        if structure_has_hp(s["type"]):
            hp = st.session_state.structure_hp.get(pos, STRUCTURE_COMBAT[s["type"]]["hp"])
            return f"{team_initial}{s['emoji']}{hp}"
        return f"{team_initial}{s['emoji']}"

    # paths
    if st.session_state.phase == "play":
        if pos in st.session_state.paths[TEAM_A] or pos in st.session_state.paths[TEAM_B]:
            return PATH_EMOJI

    return "·"

def place_card(card_name: str):
    if st.session_state.phase != "build":
        return
    if st.session_state.selected is None:
        return

    pos = st.session_state.selected
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

    if structure_has_hp(card["type"]):
        st.session_state.structure_hp[pos] = STRUCTURE_COMBAT[card["type"]]["hp"]


# =========================================================
# App start
# =========================================================
ss_init()
if len(st.session_state.placements) == 0:
    init_castles()

# =========================================================
# UI Styling
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
      .pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        border: 1px solid rgba(0,0,0,0.12); font-size: 12px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("War Game (Deployable)")
st.caption("BUILD: place cards. PLAY: Next Move = move troops + auto-attack once (no diagonals).")

# =========================================================
# Sidebar
# =========================================================
with st.sidebar:
    st.header("Controls")

    if st.button("🔄 Reset Game"):
        reset_game()

    st.divider()
    st.write("Phase:")
    st.subheader("BUILD" if st.session_state.phase == "build" else "PLAY")

    winner = check_winner()
    if winner:
        st.success(f"🏆 {winner} wins! (Enemy castle destroyed)")
        st.write("Press Reset Game to play again.")
    else:
        if st.session_state.phase == "build":
            if st.button("▶️ Start Play (spawn troops)"):
                st.session_state.phase = "play"
                st.session_state.selected = None
                start_play()
        else:
            if st.button("➡️ Next Move"):
                next_move()

    st.divider()
    st.write("Build placing for:")
    st.subheader(st.session_state.turn)
    if st.session_state.phase == "build":
        if st.button("🔁 Switch Player"):
            st.session_state.turn = enemy(st.session_state.turn)

    st.divider()
    st.markdown("**Deploy notes:**")
    st.write("Put this file as `app.py` and add `requirements.txt` with `streamlit`.")

# =========================================================
# Main Board
# =========================================================
st.write("### Board")
if st.session_state.phase == "build":
    st.info("Click a square → place a card. Castles are pre-placed.")
else:
    st.info("Press **Next Move**. After moving, every troop/tower attacks once.")

n = st.session_state.size
disable_click = (st.session_state.phase != "build")

for r in range(n):
    cols = st.columns(n, gap="small")
    for c in range(n):
        label = square_label(r, c)
        is_selected = (st.session_state.selected == (r, c))
        btn_text = f"[{label}]" if is_selected else f" {label} "
        if cols[c].button(btn_text, key=f"sq_{r}_{c}", use_container_width=True, disabled=disable_click):
            st.session_state.selected = (r, c)

# =========================================================
# Placement Cards
# =========================================================
if st.session_state.phase == "build" and st.session_state.selected is not None:
    team = st.session_state.turn
    team_cls = "red" if team == TEAM_A else "blue"
    r, c = st.session_state.selected

    st.write("### Place a card")
    st.caption(f"Selected: row {r+1}, col {c+1} • Team: {team}")

    card_cols = st.columns(len(CARD_DEFS), gap="small")
    for i, (name, info) in enumerate(CARD_DEFS.items()):
        with card_cols[i]:
            if info["type"] == "Barracks":
                desc = f"Spawns: {info['spawns']} • HP {STRUCTURE_COMBAT['Barracks']['hp']}"
            elif info["type"] == "Tower":
                desc = f"Range {STRUCTURE_COMBAT['Tower']['range']} • HP {STRUCTURE_COMBAT['Tower']['hp']}"
            else:
                desc = ""
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

# =========================================================
# Status footer
# =========================================================
st.write("---")
left = get_castle_pos(TEAM_A)
right = get_castle_pos(TEAM_B)
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f'<span class="pill">🏰 {TEAM_A} HP: {st.session_state.structure_hp.get(left, 0)}</span>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<span class="pill">🏰 {TEAM_B} HP: {st.session_state.structure_hp.get(right, 0)}</span>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<span class="pill">Troops: {len(st.session_state.troops)}</span>', unsafe_allow_html=True)