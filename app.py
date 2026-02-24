# app.py  (deployable + sounds)
import base64
import io
import math
import random
import struct
import streamlit as st

st.set_page_config(page_title="War Game (Deployable + Sounds)", layout="centered")

# =========================================================
# CONFIG (easy to extend)
# =========================================================
BOARD_SIZE = 7
TEAM_A, TEAM_B = "Red", "Blue"
TEAMS = [TEAM_A, TEAM_B]
PATH_EMOJI = "▫️"

CARD_DEFS = {
    "Melee Barracks":  {"type": "Barracks", "spawns": "Melee",  "emoji": "⚔️"},
    "Archer Barracks": {"type": "Barracks", "spawns": "Archer", "emoji": "🏹"},
    "Tower":           {"type": "Tower",    "spawns": None,     "emoji": "🗼"},
}

UNIT_DEFS = {
    "Melee":  {"emoji": "🗡️", "hp": 2, "range": 1, "move_pattern": [1, 1, 2], "respawn_new_path": True},
    "Archer": {"emoji": "🏹", "hp": 2, "range": 2, "move_pattern": [1],       "respawn_new_path": True},
}

STRUCTURE_COMBAT = {
    "Barracks": {"hp": 4,  "range": 0, "attacks": False},
    "Tower":    {"hp": 3,  "range": 3, "attacks": True},
    "Castle":   {"hp": 10, "range": 0, "attacks": False},
}

# =========================================================
# SOUND ENGINE (pure python -> base64 wav -> HTML autoplay)
# =========================================================
def _tone_wav_bytes(
    freqs,
    duration_s=0.12,
    sample_rate=22050,
    volume=0.25,
    wave="square",
):
    """
    Generate a tiny mono WAV with 16-bit PCM.
    freqs: number or list of numbers (Hz). If list, plays as a little sequence.
    """
    if isinstance(freqs, (int, float)):
        freqs = [float(freqs)]
    else:
        freqs = [float(x) for x in freqs]

    # split duration across notes
    note_dur = max(0.03, duration_s / len(freqs))
    samples = []
    for f in freqs:
        n = int(note_dur * sample_rate)
        for i in range(n):
            t = i / sample_rate
            if wave == "sine":
                v = math.sin(2 * math.pi * f * t)
            else:
                # square
                v = 1.0 if math.sin(2 * math.pi * f * t) >= 0 else -1.0
            # tiny fade to avoid clicks
            fade = min(1.0, i / (0.01 * sample_rate)) * min(1.0, (n - i) / (0.01 * sample_rate))
            v = v * fade
            samples.append(int(volume * 32767 * v))

    # WAV header
    buf = io.BytesIO()
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_bytes = len(samples) * 2

    def w(fmt, *vals):
        buf.write(struct.pack(fmt, *vals))

    buf.write(b"RIFF")
    w("<I", 36 + data_bytes)
    buf.write(b"WAVE")

    buf.write(b"fmt ")
    w("<I", 16)                # fmt chunk size
    w("<H", 1)                 # PCM
    w("<H", num_channels)
    w("<I", sample_rate)
    w("<I", byte_rate)
    w("<H", block_align)
    w("<H", bits_per_sample)

    buf.write(b"data")
    w("<I", data_bytes)
    for s in samples:
        w("<h", s)

    return buf.getvalue()

def play_sound(sound_key: str):
    """
    sound_key -> pre-defined beep patterns.
    Uses an HTML audio tag with autoplay.
    """
    patterns = {
        "place":   [880, 1320],
        "start":   [660, 880, 1320],
        "move":    [440],
        "hit":     [220, 220],
        "destroy": [196, 147, 98],
        "win":     [523, 659, 784, 1046],
    }
    freqs = patterns.get(sound_key, [440])
    wav = _tone_wav_bytes(freqs, duration_s=0.18, volume=0.22, wave="square")
    b64 = base64.b64encode(wav).decode("utf-8")
    st.markdown(
        f"""
        <audio autoplay>
          <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True,
    )

def queue_sound(sound_key: str):
    # store one sound to play this rerun
    st.session_state._sound_to_play = sound_key

def flush_sound():
    key = st.session_state.get("_sound_to_play")
    if key:
        play_sound(key)
        st.session_state._sound_to_play = None


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
        st.session_state.placements = {}
    if "structure_hp" not in st.session_state:
        st.session_state.structure_hp = {}
    if "troops" not in st.session_state:
        st.session_state.troops = []
    if "paths" not in st.session_state:
        st.session_state.paths = {TEAM_A: set(), TEAM_B: set()}
    if "next_id" not in st.session_state:
        st.session_state.next_id = 1

    if "_sound_to_play" not in st.session_state:
        st.session_state._sound_to_play = None


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
    queue_sound("start")


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
    queue_sound("start")


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
    destroyed_any = False
    dead = [pos for pos, hp in st.session_state.structure_hp.items() if hp <= 0]
    for pos in dead:
        if pos in st.session_state.placements:
            del st.session_state.placements[pos]
        del st.session_state.structure_hp[pos]
        destroyed_any = True

    return destroyed_any

def auto_attack_once():
    troops = list(st.session_state.troops)
    structures = list(all_structures())

    troop_dmg = {t["id"]: 0 for t in troops}
    struct_dmg = {}

    any_damage = False

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
            any_damage = True

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
            any_damage = True

    apply_damage_simultaneous(troop_dmg, struct_dmg)
    destroyed_any = cleanup_deaths_and_respawns()
    rebuild_paths_sets()

    # sound selection priority
    if destroyed_any:
        queue_sound("destroy")
    elif any_damage:
        queue_sound("hit")

def next_move():
    move_troops()
    queue_sound("move")
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

    if pos in mp:
        troops_here = mp[pos]
        teams_here = {t["team"] for t in troops_here}
        if len(teams_here) > 1:
            return "💥"
        t0 = troops_here[0]
        team_initial = "R" if t0["team"] == TEAM_A else "B"
        u = UNIT_DEFS[t0["unit"]]
        return f"{team_initial}{u['emoji']}{t0['hp']}"

    s = st.session_state.placements.get(pos)
    if s:
        team_initial = "R" if s["team"] == TEAM_A else "B"
        if structure_has_hp(s["type"]):
            hp = st.session_state.structure_hp.get(pos, STRUCTURE_COMBAT[s["type"]]["hp"])
            return f"{team_initial}{s['emoji']}{hp}"
        return f"{team_initial}{s['emoji']}"

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

    queue_sound("place")


# =========================================================
# App start
# =========================================================
if "initialized" not in st.session_state:
    ss_init()
    init_castles()
    st.session_state.initialized = True
else:
    ss_init()

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

st.title("War Game (Deployable + Sounds)")
st.caption("BUILD: place cards. PLAY: Next Move = move troops + auto-attack once. Sound effects included.")

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
        queue_sound("win")
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
    st.markdown("**Deploy files:**")
    st.code("app.py\nrequirements.txt (streamlit)", language="text")

# =========================================================
# Main Board
# =========================================================
st.write("### Board")
if st.session_state.phase == "build":
    st.info("Click a square → place a card. Castles are pre-placed.")
else:
    st.info("Press **Next Move**. After moving, every troop/tower attacks once (no diagonals).")

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

# Placement cards
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

# Status footer
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

# Play the queued sound LAST so it triggers on the final rendered page
flush_sound()