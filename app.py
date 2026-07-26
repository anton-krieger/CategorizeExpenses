"""CategorizeExpenses – interactive tag-based expense browser.

Local-only Streamlit app for exploring, searching, and tagging bank export
entries. Reads the source CSV from data/ (never modified) and stores tags in
two private files that stay local:

    data/tags.json           tag name -> color (hex), assigned once at creation
    data/tagged_entries.csv  entry_id -> tags   (the only file this app writes)

Security: this app must only ever be reachable on localhost. The bundled
.streamlit/config.toml pins server.address to 127.0.0.1 — do not override
that with --server.address when running the app.

Run with:
    source .venv/bin/activate
    streamlit run app.py
"""

import glob
import hashlib
import json
import os
import random

import pandas as pd
import streamlit as st

DATA_DIR = "data"
TAGS_DEF_PATH = os.path.join(DATA_DIR, "tags.json")
TAGGED_ENTRIES_PATH = os.path.join(DATA_DIR, "tagged_entries.csv")

DATE_COL = "Buchungstag"
VALUTA_COL = "Valutadatum"
NAME_COL = "Beguenstigter/Zahlungspflichtiger"
PURPOSE_COL = "Verwendungszweck"
AMOUNT_COL = "Betrag"

st.set_page_config(page_title="Categorize Expenses", layout="wide")


# ---------- Source file discovery ----------
def find_source_csv() -> str | None:
    """Locate the single bank-export CSV in data/, excluding our own private files."""
    candidates = [
        p
        for p in glob.glob(os.path.join(DATA_DIR, "*.csv")) + glob.glob(os.path.join(DATA_DIR, "*.CSV"))
        if os.path.basename(p) != os.path.basename(TAGGED_ENTRIES_PATH)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return st.selectbox("Multiple CSV files found in data/ — choose one", sorted(candidates))
    return None


# ---------- Data loading ----------
def make_entry_ids(df: pd.DataFrame) -> list[str]:
    """Stable id per row: hash of key fields + an occurrence counter so that
    genuine duplicate transactions (same date/purpose/amount/name) still get
    distinct, reproducible ids across re-runs of the same source file."""
    counters: dict[tuple, int] = {}
    ids = []
    for _, row in df.iterrows():
        key = (
            row.get(DATE_COL, ""),
            row.get(VALUTA_COL, ""),
            row.get(PURPOSE_COL, ""),
            row.get(AMOUNT_COL, ""),
            row.get(NAME_COL, ""),
        )
        occurrence = counters.get(key, 0)
        counters[key] = occurrence + 1
        raw = "|".join(str(part) for part in (*key, occurrence))
        ids.append(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12])
    return ids


@st.cache_data
def load_source(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str)
    df["entry_id"] = make_entry_ids(df)
    df["amount_num"] = (
        df[AMOUNT_COL].fillna("0").str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    )
    df["date_parsed"] = pd.to_datetime(df[DATE_COL], format="%d.%m.%y", errors="coerce")
    return df


def load_tag_defs() -> dict:
    if os.path.isfile(TAGS_DEF_PATH):
        with open(TAGS_DEF_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_tag_defs(tag_defs: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TAGS_DEF_PATH, "w", encoding="utf-8") as fh:
        json.dump(tag_defs, fh, ensure_ascii=False, indent=2)


def load_entry_tags() -> dict:
    """entry_id -> list[str] tags, loaded from the private CSV."""
    if os.path.isfile(TAGGED_ENTRIES_PATH):
        tdf = pd.read_csv(TAGGED_ENTRIES_PATH, dtype=str).fillna("")
        return {row["entry_id"]: [t for t in row["tags"].split("|") if t] for _, row in tdf.iterrows()}
    return {}


def save_entry_tags(entry_tags: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = [{"entry_id": eid, "tags": "|".join(tags)} for eid, tags in entry_tags.items() if tags]
    pd.DataFrame(rows, columns=["entry_id", "tags"]).to_csv(TAGGED_ENTRIES_PATH, index=False)


def random_tag_color() -> str:
    r, g, b = (random.randint(50, 190) for _ in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def tag_badges_html(tag_names: list[str], tag_defs: dict) -> str:
    return " ".join(
        f'<span style="background:{tag_defs.get(t, "#888")};padding:2px 8px;'
        f'border-radius:10px;margin-right:4px;color:white;font-size:12px">{t}</span>'
        for t in tag_names
    )


# ---------- App ----------
source_path = find_source_csv()
if not source_path:
    st.error(f"No source CSV found in `{DATA_DIR}/`. Place your bank export CSV there and reload.")
    st.stop()

if "tag_defs" not in st.session_state:
    st.session_state.tag_defs = load_tag_defs()
if "entry_tags" not in st.session_state:
    st.session_state.entry_tags = load_entry_tags()
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()

df = load_source(source_path)

st.title("Categorize Expenses")

col1, col2, col3 = st.columns([1, 2, 1])

# ---------- Column 1: filter by tag / no-tag ----------
with col1:
    st.subheader("Filter")
    all_tag_names = sorted(st.session_state.tag_defs.keys())
    view_mode = st.radio("View", ["All entries", "No tags"], index=0)
    selected_tag_filter = st.multiselect("Filter by tag(s)", all_tag_names)

    if all_tag_names:
        st.markdown("**Defined tags**")
        st.markdown(tag_badges_html(all_tag_names, st.session_state.tag_defs), unsafe_allow_html=True)


def matches_filter(entry_id: str) -> bool:
    tags = st.session_state.entry_tags.get(entry_id, [])
    if view_mode == "No tags":
        return len(tags) == 0
    if selected_tag_filter:
        return any(t in tags for t in selected_tag_filter)
    return True


filtered = df[df["entry_id"].apply(matches_filter)]

# ---------- Column 2: search + table + tag editor ----------
with col2:
    st.subheader("Entries")
    query = st.text_input("Search name / purpose").strip().lower()
    if query:
        mask = (
            filtered[NAME_COL].fillna("").str.lower().str.contains(query, regex=False)
            | filtered[PURPOSE_COL].fillna("").str.lower().str.contains(query, regex=False)
        )
        filtered = filtered[mask]

    sort_col1, sort_col2 = st.columns([2, 1])
    with sort_col1:
        sort_by = st.selectbox("Sort by", ["Date", "Price"])
    with sort_col2:
        ascending = st.checkbox("Ascending", value=False)
    sort_key = "date_parsed" if sort_by == "Date" else "amount_num"
    filtered = filtered.sort_values(sort_key, ascending=ascending)

    filtered_ids = filtered["entry_id"].tolist()

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Select all in view"):
            st.session_state.selected_ids.update(filtered_ids)
            st.rerun()
    with btn_col2:
        if st.button("Clear selection"):
            st.session_state.selected_ids.difference_update(filtered_ids)
            st.rerun()

    display_df = filtered[["entry_id", DATE_COL, NAME_COL, PURPOSE_COL, "amount_num"]].copy()
    display_df.insert(0, "select", display_df["entry_id"].isin(st.session_state.selected_ids))
    display_df["tags"] = display_df["entry_id"].map(lambda eid: ", ".join(st.session_state.entry_tags.get(eid, [])))
    display_df = display_df.rename(columns={DATE_COL: "Date", NAME_COL: "Name", PURPOSE_COL: "Purpose", "amount_num": "Price"})

    edited = st.data_editor(
        display_df,
        hide_index=True,
        disabled=["Date", "Name", "Purpose", "Price", "tags", "entry_id"],
        column_config={
            "entry_id": None,
            "Price": st.column_config.NumberColumn(format="%.2f €"),
        },
        key="entries_editor",
        width="stretch",
    )

    # Sync checkbox edits for currently visible rows back into persistent selection.
    for _, row in edited.iterrows():
        if row["select"]:
            st.session_state.selected_ids.add(row["entry_id"])
        else:
            st.session_state.selected_ids.discard(row["entry_id"])

    selected_ids = [eid for eid in filtered_ids if eid in st.session_state.selected_ids]
    st.caption(f"{len(st.session_state.selected_ids)} selected in total ({len(selected_ids)} in current view)")

    st.markdown("**Apply tags to selection**")
    apply_col1, apply_col2 = st.columns(2)
    with apply_col1:
        existing_choice = st.multiselect("Existing tags", all_tag_names, key="apply_existing")
    with apply_col2:
        new_tag_name = st.text_input("New tag name")

    if st.button("Apply to selected", disabled=not st.session_state.selected_ids):
        tags_to_apply = list(existing_choice)
        new_tag_name = new_tag_name.strip()
        if new_tag_name:
            if new_tag_name not in st.session_state.tag_defs:
                st.session_state.tag_defs[new_tag_name] = random_tag_color()
                save_tag_defs(st.session_state.tag_defs)
            tags_to_apply.append(new_tag_name)

        if tags_to_apply:
            for eid in st.session_state.selected_ids:
                current = set(st.session_state.entry_tags.get(eid, []))
                current.update(tags_to_apply)
                st.session_state.entry_tags[eid] = sorted(current)
            save_entry_tags(st.session_state.entry_tags)
            st.success(f"Applied {tags_to_apply} to {len(st.session_state.selected_ids)} entries")
            st.rerun()
        else:
            st.warning("Pick at least one existing tag or type a new tag name.")

# ---------- Column 3: stats (follows the current filter + search) ----------
with col3:
    st.subheader("Stats")
    st.caption("Reflects the current tag filter + search")
    nums = filtered["amount_num"]
    income = nums[nums > 0].sum()
    expense = nums[nums < 0].sum()
    st.metric("Income", f"{income:,.2f} EUR")
    st.metric("Expense", f"{expense:,.2f} EUR")
    st.metric("Net", f"{nums.sum():,.2f} EUR")

    st.markdown("**By year**")
    by_year = filtered.groupby(filtered["date_parsed"].dt.year)["amount_num"].sum()
    st.dataframe(by_year.rename("Total"), width="stretch")

    st.markdown("**By month**")
    by_month = filtered.groupby(filtered["date_parsed"].dt.to_period("M"))["amount_num"].sum()
    st.dataframe(by_month.rename("Total"), width="stretch")
