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
import re
from collections import Counter

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
def find_source_csvs() -> list[str]:
    """Locate bank-export CSVs organized in year subfolders, e.g. data/2024/, data/2025/.

    Every CSV found in each numeric-named subfolder of data/ is treated as a
    source file and combined into one dataset. Loose CSVs directly in data/
    (not inside a year folder) are ignored so stray/duplicate downloads don't
    get picked up by accident.
    """
    year_dirs = sorted(
        d for d in glob.glob(os.path.join(DATA_DIR, "*")) if os.path.isdir(d) and os.path.basename(d).isdigit()
    )
    candidates = []
    for year_dir in year_dirs:
        candidates.extend(glob.glob(os.path.join(year_dir, "*.csv")))
        candidates.extend(glob.glob(os.path.join(year_dir, "*.CSV")))
    return sorted(set(candidates))


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
def load_source(paths: tuple[str, ...]) -> pd.DataFrame:
    """Load and combine one or more bank-export CSVs (one per year folder)."""
    frames = [pd.read_csv(path, sep=";", encoding="latin-1", dtype=str) for path in paths]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
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


def top_words(df_subset: pd.DataFrame, top_n: int = 80) -> list[str]:
    """Most frequent words across the name and purpose fields, for search inspiration."""
    stopwords = {
        "bei", "ihr", "ihre", "der", "die", "das", "und", "von", "fur", "für",
        "mit", "den", "des", "dem", "auf", "im", "zu", "am", "aus", "fuer",
    }
    text = " ".join(df_subset[NAME_COL].fillna("")) + " " + " ".join(df_subset[PURPOSE_COL].fillna(""))
    tokens = [t for t in re.findall(r"[a-zA-ZäöüÄÖÜß]+", text.lower()) if len(t) >= 3 and t not in stopwords]
    return [word for word, _ in Counter(tokens).most_common(top_n)]


def tag_badges_html(tag_names: list[str], tag_defs: dict) -> str:
    return " ".join(
        f'<span style="background:{tag_defs.get(t, "#888")};padding:2px 8px;'
        f'border-radius:10px;margin-right:4px;color:white;font-size:12px">{t}</span>'
        for t in tag_names
    )


# ---------- App ----------
source_paths = find_source_csvs()
if not source_paths:
    st.error(
        f"No source CSVs found under `{DATA_DIR}/<year>/`. "
        f"Place your bank export CSVs in year-named subfolders (e.g. `{DATA_DIR}/2024/`, `{DATA_DIR}/2025/`) and reload."
    )
    st.stop()

if "tag_defs" not in st.session_state:
    st.session_state.tag_defs = load_tag_defs()
if "entry_tags" not in st.session_state:
    st.session_state.entry_tags = load_entry_tags()
if "editor_nonce" not in st.session_state:
    st.session_state.editor_nonce = 0
if "select_default" not in st.session_state:
    st.session_state.select_default = False
if "last_view_sig" not in st.session_state:
    st.session_state.last_view_sig = None
if "review_nonce" not in st.session_state:
    st.session_state.review_nonce = 0
if "last_review_tag" not in st.session_state:
    st.session_state.last_review_tag = None
if "review_select_default" not in st.session_state:
    st.session_state.review_select_default = False

df = load_source(tuple(source_paths))

st.title("Categorize Expenses")

col1, col2, col3 = st.columns([1, 2, 1])

# ---------- Column 1: filter by tag / no-tag ----------
with col1:
    st.subheader("Filter")
    all_tag_names = sorted(st.session_state.tag_defs.keys())

    available_years = sorted(df["date_parsed"].dt.year.dropna().unique().astype(int).tolist())
    year_choice = st.selectbox("Year", ["All years"] + [str(y) for y in available_years])

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


if year_choice != "All years":
    df = df[df["date_parsed"].dt.year == int(year_choice)]

filtered = df[df["entry_id"].apply(matches_filter)]

# ---------- Column 2: search + table + tag editor ----------
with col2:
    st.subheader("Entries")

    st.caption("Top words in names & purposes (current tag filter) — for search inspiration")
    with st.container(height=100, border=True):
        st.write(" ".join(top_words(filtered)) or "—")

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

    # Selection is scoped to the current view. Whenever the view changes
    # (tag filter, no-tag mode, search text, or sort), reset the selection so
    # stale rows from a previous search can never be tagged by accident.
    view_sig = (year_choice, view_mode, tuple(sorted(selected_tag_filter)), query, sort_by, ascending)
    if view_sig != st.session_state.last_view_sig:
        st.session_state.last_view_sig = view_sig
        st.session_state.select_default = False
        st.session_state.editor_nonce += 1

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Select all in view"):
            st.session_state.select_default = True
            st.session_state.editor_nonce += 1
            st.rerun()
    with btn_col2:
        if st.button("Clear selection"):
            st.session_state.select_default = False
            st.session_state.editor_nonce += 1
            st.rerun()

    display_df = filtered[["entry_id", DATE_COL, NAME_COL, PURPOSE_COL, "amount_num"]].copy()
    display_df.insert(0, "select", st.session_state.select_default)
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
        key=f"entries_editor_{st.session_state.editor_nonce}",
        width="stretch",
    )

    selected_ids = edited.loc[edited["select"], "entry_id"].tolist()
    st.caption(f"{len(selected_ids)} selected in current view")

    st.markdown("**Apply tags to selection**")
    apply_col1, apply_col2 = st.columns(2)
    with apply_col1:
        existing_choice = st.multiselect("Existing tags", all_tag_names, key="apply_existing")
    with apply_col2:
        new_tag_name = st.text_input("New tag name")

    if st.button("Apply to selected", disabled=not selected_ids):
        tags_to_apply = list(existing_choice)
        new_tag_name = new_tag_name.strip()
        if new_tag_name:
            if new_tag_name not in st.session_state.tag_defs:
                st.session_state.tag_defs[new_tag_name] = random_tag_color()
                save_tag_defs(st.session_state.tag_defs)
            tags_to_apply.append(new_tag_name)

        if tags_to_apply:
            for eid in selected_ids:
                current = set(st.session_state.entry_tags.get(eid, []))
                current.update(tags_to_apply)
                st.session_state.entry_tags[eid] = sorted(current)
            save_entry_tags(st.session_state.entry_tags)
            # Reset the selection after tagging so the next action starts clean.
            st.session_state.select_default = False
            st.session_state.editor_nonce += 1
            st.success(f"Applied {tags_to_apply} to {len(selected_ids)} entries")
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


# ---------- Tag review / audit (full width) ----------
st.divider()
with st.expander("Tag review / audit — inspect and correct tagged entries", expanded=False):
    if not all_tag_names:
        st.info("No tags defined yet.")
    else:
        # Overview: how many entries carry each tag. An unexpectedly high count
        # can be a sign of accidental over-tagging from the earlier selection bug.
        counts = {t: sum(1 for tags in st.session_state.entry_tags.values() if t in tags) for t in all_tag_names}
        overview = pd.DataFrame({"tag": list(counts.keys()), "entries": list(counts.values())})
        overview = overview.sort_values("entries", ascending=False)
        st.markdown("**Entries per tag**")
        st.dataframe(overview, hide_index=True, width="stretch")

        review_tag = st.selectbox("Show all entries tagged", all_tag_names, key="review_tag_select")

        multi_only = st.checkbox(
            "Only show entries with multiple tags",
            key="review_multi_only",
            help="Useful for spotting entries that were tagged more than once.",
        )

        # Reset the review selection whenever the reviewed tag or filter changes.
        review_sig = (review_tag, multi_only)
        if st.session_state.last_review_tag != review_sig:
            st.session_state.last_review_tag = review_sig
            st.session_state.review_select_default = False
            st.session_state.review_nonce += 1

        tagged_ids = [
            eid
            for eid, tags in st.session_state.entry_tags.items()
            if review_tag in tags and (not multi_only or len(tags) > 1)
        ]
        review_rows = df[df["entry_id"].isin(tagged_ids)].sort_values("date_parsed")

        suffix = " with multiple tags" if multi_only else ""
        st.caption(
            f"{len(review_rows)} entr{'y' if len(review_rows) == 1 else 'ies'} tagged '{review_tag}'{suffix}"
        )

        if len(review_rows):
            rbtn_col1, rbtn_col2 = st.columns(2)
            with rbtn_col1:
                if st.button("Select all viewed", key="review_select_all"):
                    st.session_state.review_select_default = True
                    st.session_state.review_nonce += 1
                    st.rerun()
            with rbtn_col2:
                if st.button("Clear selection", key="review_clear"):
                    st.session_state.review_select_default = False
                    st.session_state.review_nonce += 1
                    st.rerun()

            review_df = review_rows[["entry_id", DATE_COL, NAME_COL, PURPOSE_COL, "amount_num"]].copy()
            review_df.insert(0, "remove", st.session_state.review_select_default)
            review_df["all tags"] = review_df["entry_id"].map(
                lambda eid: ", ".join(st.session_state.entry_tags.get(eid, []))
            )
            review_df = review_df.rename(
                columns={DATE_COL: "Date", NAME_COL: "Name", PURPOSE_COL: "Purpose", "amount_num": "Price"}
            )

            review_edited = st.data_editor(
                review_df,
                hide_index=True,
                disabled=["Date", "Name", "Purpose", "Price", "all tags", "entry_id"],
                column_config={
                    "entry_id": None,
                    "Price": st.column_config.NumberColumn(format="%.2f €"),
                    "remove": st.column_config.CheckboxColumn(f"remove '{review_tag}'"),
                },
                key=f"review_editor_{st.session_state.review_nonce}",
                width="stretch",
            )

            to_remove = review_edited.loc[review_edited["remove"], "entry_id"].tolist()
            if st.button(f"Remove '{review_tag}' from selected", disabled=not to_remove):
                for eid in to_remove:
                    remaining = [t for t in st.session_state.entry_tags.get(eid, []) if t != review_tag]
                    if remaining:
                        st.session_state.entry_tags[eid] = remaining
                    else:
                        st.session_state.entry_tags.pop(eid, None)
                save_entry_tags(st.session_state.entry_tags)
                st.session_state.review_select_default = False
                st.session_state.review_nonce += 1
                st.success(
                    f"Removed '{review_tag}' from {len(to_remove)} "
                    f"entr{'y' if len(to_remove) == 1 else 'ies'}"
                )
                st.rerun()

        st.divider()
        st.markdown("**Delete a tag entirely**")
        st.caption(
            "Removes the selected tag from its definition and from every entry that carries it. "
            "This cannot be undone."
        )
        confirm_delete = st.checkbox(
            f"Yes, permanently delete '{review_tag}'", key="confirm_delete_tag"
        )
        if st.button(
            f"Delete tag '{review_tag}' from all entries",
            type="primary",
            disabled=not confirm_delete,
        ):
            affected = 0
            for eid in list(st.session_state.entry_tags.keys()):
                remaining = [t for t in st.session_state.entry_tags[eid] if t != review_tag]
                if len(remaining) != len(st.session_state.entry_tags[eid]):
                    affected += 1
                if remaining:
                    st.session_state.entry_tags[eid] = remaining
                else:
                    st.session_state.entry_tags.pop(eid, None)
            st.session_state.tag_defs.pop(review_tag, None)
            save_entry_tags(st.session_state.entry_tags)
            save_tag_defs(st.session_state.tag_defs)
            st.session_state.review_select_default = False
            st.session_state.last_review_tag = None
            st.session_state.review_nonce += 1
            st.success(
                f"Deleted tag '{review_tag}' (removed from {affected} "
                f"entr{'y' if affected == 1 else 'ies'})"
            )
            st.rerun()
