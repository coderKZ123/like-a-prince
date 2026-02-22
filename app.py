import streamlit as st


st.set_page_config(page_title="War Game", layout="centered")


# --- Session state ---
if "size" not in st.session_state:
   st.session_state.size = 5
if "selected" not in st.session_state:
   st.session_state.selected = None
if "turn" not in st.session_state:
   st.session_state.turn = "Red"


def reset():
   st.session_state.selected = None
   st.session_state.turn = "Red"


# --- Header ---
st.title("❄️ Snowday War Game (Dummy UI)")
st.caption("Today we ship first. Rules come later.")


with st.sidebar:
   st.header("Controls")
   st.write("This is a *demo UI*.")
   if st.button("🔄 Reset"):
       reset()
   if st.button("➡️ Next Turn"):
       st.session_state.turn = "Blue" if st.session_state.turn == "Red" else "Red"
   st.divider()
   st.write("Turn:")
   st.subheader(st.session_state.turn)


st.write("### Board")
st.info("Click any square. For now it just selects it.")


# --- Board UI ---
size = st.session_state.size
for r in range(size):
   cols = st.columns(size, gap="small")
   for c in range(size):
       label = "·"  # placeholder
       is_selected = (st.session_state.selected == (r, c))
       btn_text = f"[{label}]" if is_selected else f" {label} "


       if cols[c].button(btn_text, key=f"sq_{r}_{c}", use_container_width=True):
           st.session_state.selected = (r, c)


# --- Footer ---
st.write("---")
if st.session_state.selected is None:
   st.write("Selected: *(none)*")
else:
   r, c = st.session_state.selected
   st.success(f"Selected: row {r+1}, col {c+1}")
