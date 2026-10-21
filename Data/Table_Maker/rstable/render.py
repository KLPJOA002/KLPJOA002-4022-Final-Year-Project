"""Table -> LaTeX (booktabs + makecell), HTML preview and tidy CSV.

One grid builder, two outputs: the HTML preview shows exactly the cells, spans,
rules and bolding the LaTeX source has.
"""
from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field

import pandas as pd

from rsplot import registry as reg
from rsplot.data import Dataset
from rsplot.pipeline import METRIC, X_VALUE

from .spec import TableSpec
from .table import DUP, INTERVAL, Cell, Table, _isnan, key_label, value_text

# ------------------------------------------------------------- outputs --
_TEX = {"%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_", "$": r"\$", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}",
        "°": r"\textdegree{}", "±": r"$\pm$", "≥": r"$\geq$", "≤": r"$\leq$", "×": r"$\times$",
        "−": r"$-$", "–": "--", "—": "---", "µ": r"\textmu{}", "²": r"\textsuperscript{2}",
        "³": r"\textsuperscript{3}", "½": r"\textonehalf{}", "α": r"$\alpha$",
        "δ": r"$\delta$", "∈": r"$\in$", "→": r"$\rightarrow$"}


class TexOut:
    kind = "tex"
    pm, dash, missing = r"$\pm$", "--", "--"

    def __init__(self, math_minus: bool = True):
        self.math_minus = math_minus

    def esc(self, s: str) -> str:
        return "".join(_TEX.get(ch, ch) for ch in str(s))

    def num(self, s: str) -> str:
        return (r"$-$" + s[1:]) if self.math_minus and s.startswith("-") else s

    def bold(self, s: str) -> str:
        return rf"\textbf{{{s}}}"

    def small(self, s: str) -> str:
        return rf"{{\footnotesize {s}}}"

    def lines(self, parts: list[str], makecell: bool = True, stat: str = "") -> str:
        parts = [self.esc(p) for p in parts]
        if stat:
            parts.append(rf"{{\footnotesize {self.esc(stat)}}}")
        if len(parts) == 1:
            return parts[0]
        return (r"\makecell{" + r"\\".join(parts) + "}") if makecell else " ".join(parts)


class HtmlOut:
    kind = "html"
    pm, dash, missing = "±", "–", "–"

    def __init__(self, math_minus: bool = True):
        pass

    def esc(self, s: str) -> str:
        return html.escape(str(s))

    def num(self, s: str) -> str:
        return ("−" + s[1:]) if s.startswith("-") else s

    def bold(self, s: str) -> str:
        return f"<b>{s}</b>"

    def small(self, s: str) -> str:
        return f'<span class="sm">{s}</span>'

    def lines(self, parts: list[str], makecell: bool = True, stat: str = "") -> str:
        out = [self.esc(p) for p in parts]
        if stat:
            out.append(f'<span class="stat">{self.esc(stat)}</span>')
        return "<br>".join(out)


# ----------------------------------------------------------------- grid --
@dataclass
class HCell:
    text: str
    span: int = 1
    rule: bool = False     # \cmidrule under it


@dataclass
class Grid:
    align: list[str]                       # per tex column: l | r | c
    header: list[list[HCell]]
    body: list[list[str]]
    seps: list[str]                        # per body row: "" | "space" | "midrule" (before it)
    n_rowkey: int = 0
    notes: list[str] = field(default_factory=list)


def fmt_number(v: float, d: int, out) -> str:
    if _isnan(v):
        return out.missing
    s = f"{v:.{d}f}"
    if re.fullmatch(r"-0\.?0*", s):
        s = s[1:]
    return out.num(s)


def wrap_label(text: str, width: int) -> list[str]:
    """Split 'Median depth error (mm)' into balanced lines; '|' or '\\\\' force breaks."""
    if "|" in text or "\\\\" in text:
        return [p.strip() for p in re.split(r"\||\\\\", text)]
    if width <= 0 or len(text) <= width:
        return [text]
    tokens = re.findall(r"\([^)]*\)|\S+", text)
    k = min(math.ceil(len(text) / width), len(tokens))
    return _balanced(tokens, k)


def _balanced(tokens: list[str], k: int) -> list[str]:
    """Split tokens into k lines minimising the longest line (ties: earlier lines longer)."""
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def best(i: int, k: int):
        if k == 1:
            line = " ".join(tokens[i:])
            return len(line), (line,)
        out = None
        for j in range(i + 1, len(tokens) - k + 2):
            line = " ".join(tokens[i:j])
            rest_len, rest = best(j, k - 1)
            cand = (max(len(line), rest_len), (line,) + rest)
            if out is None or cand[0] < out[0]:
                out = cand
        return out
    return list(best(0, k)[1])


def metric_label(t: Table, ts: TableSpec, m: str) -> str:
    over = ts.format.header_labels.get(m)
    if over:
        return over
    return reg.axis_label(m, t.plot.style.labels if t.plot else None,
                          percent=t.percent.get(m, False))


def key_header(t: Table, ts: TableSpec, key: str) -> str:
    over = ts.format.header_labels.get(key)
    return over or key_label(key, t.plot, x_metric=t.x_metric)


def cell_parts(c: Cell | None, t: Table, ts: TableSpec, out) -> tuple[str, str]:
    """(centre text, spread text) of one cell."""
    if c is None or _isnan(c.value):
        return out.missing, ""
    st, fm = t.stat, ts.format
    d = t.decimals.get(c.metric, 2)
    centre = fmt_number(c.value, d, out)
    if c.best:
        centre = out.bold(centre)
    show = st.has_spread and not (_isnan(c.lo) or _isnan(c.hi)) and (
        st.per_trial or _isnan(c.n) or c.n >= 2)
    if not show:
        return centre, ""
    num = lambda v: fmt_number(v, d, out)
    half = (c.hi - c.lo) / 2
    f = st.fmt
    if f == "pm":
        sp = f"{out.pm} {num(half)}"
    elif f == "brackets":
        sp = f"[{num(c.lo)}, {num(c.hi)}]"
    elif f == "parens":
        sp = f"({num(c.lo)}{out.dash}{num(c.hi)})"
    elif f == "width":
        sp = f"({num(c.hi - c.lo if st.spread in INTERVAL else half)})"
    elif f == "column":
        sp = num(half) if st.spread not in INTERVAL else f"{num(c.lo)}{out.dash}{num(c.hi)}"
    else:
        sp = ""
    if sp and fm.spread_small:
        sp = out.small(sp)
    return centre, sp


def build_grid(t: Table, ts: TableSpec, out) -> Grid:
    fm, lay, o = ts.format, ts.layout, ts.output
    st = t.stat
    stat_head = st.short() if fm.stat_place in ("header", "both") else ""
    spread_col = st.fmt == "column" and st.has_spread
    n_col = fm.n_mode == "column" and bool(t.n_text)
    rk = t.row_keys
    nk = len(rk)

    # ---- alignment ----
    align = []
    for k in rk:
        p = t.ds.profile.get(k) if t.ds else None
        numeric = k in (X_VALUE, DUP) or (p is not None and p.kind == "numeric")
        align.append("r" if numeric else "l")
    per_col = 2 if spread_col else 1
    align += ["c"] * (len(t.cols) * per_col) + (["c"] if n_col else [])

    # ---- header ----
    header: list[list[HCell]] = []
    ck = t.col_keys
    levels = max(len(ck), 1)
    stat_on_metric_row = METRIC in rk and stat_head
    for lev in range(levels):
        last = lev == levels - 1
        row: list[HCell] = []
        if last:
            for k in rk:
                lab = wrap_label(key_header(t, ts, k), fm.wrap)
                row.append(HCell(out.lines(lab, o.makecell,
                                           stat_head if (k == METRIC and stat_on_metric_row)
                                           else "")))
        else:
            row += [HCell("") for _ in rk]
        if not ck:
            text = ts.format.header_labels.get("__value__") or "Value"
            row.append(HCell(out.lines(wrap_label(text, fm.wrap), o.makecell), per_col,
                             rule=spread_col))
        else:
            j = 0
            while j < len(t.cols):
                prefix = t.cols[j][:lev + 1]
                span = 1
                while j + span < len(t.cols) and t.cols[j + span][:lev + 1] == prefix:
                    span += 1
                key, val = ck[lev], prefix[-1]
                if key == METRIC:
                    text = out.lines(wrap_label(metric_label(t, ts, val), fm.wrap), o.makecell,
                                     stat_head)
                else:
                    # a heading spanning several columns has room: wrap only at a forced break
                    label = value_text(key, val, t.plot, fm.value_labels)
                    text = out.lines(wrap_label(label, fm.wrap if span == 1 else 0), o.makecell)
                row.append(HCell(text, span * per_col, rule=not last or spread_col))
                j += span
        if n_col:
            row.append(HCell(out.esc("n") if last else ""))
        header.append(row)
    if spread_col:
        c_word = st.short()
        sub = [HCell("") for _ in rk]
        for _ in t.cols:
            sub += [HCell(out.esc(c_word)), HCell(out.esc(st.spread_head()))]
        if n_col:
            sub.append(HCell(""))
        header.append(sub)
        # row-key headings go on the lowest row
        for i in range(nk):
            header[-1][i], header[-2][i] = header[-2][i], HCell("")
        if n_col:
            header[-1][-1], header[-2][-1] = header[-2][-1], HCell("")

    # ---- body ----
    body, seps = [], []
    prev = None
    firsts = [keys[0] for keys in t.rows] if nk > 1 else []
    grouped = len(set(firsts)) < len(firsts)
    for r, keys in enumerate(t.rows):
        cells = []
        for i, (k, v) in enumerate(zip(rk, keys)):
            same_prefix = prev is not None and prev[:i + 1] == keys[:i + 1]
            if not lay.repeat_labels and same_prefix and i < nk - 1:
                cells.append("")
            elif k == METRIC:
                cells.append(out.lines([metric_label(t, ts, v)], False))
            else:
                cells.append(out.esc(value_text(k, v, t.plot, fm.value_labels,
                                                x_decimals=_x_decimals(t))))
        ns = []
        for c in range(len(t.cols)):
            cell = t.cells.get((r, c))
            centre, sp = cell_parts(cell, t, ts, out)
            if spread_col:
                cells += [centre, sp]
            else:
                cells.append(f"{centre} {sp}".strip())
            if cell is not None and not _isnan(cell.n):
                ns.append(int(cell.n))
        if n_col:
            cells.append(out.missing if not ns else
                         str(ns[0]) if min(ns) == max(ns) else f"{min(ns)}{out.dash}{max(ns)}")
        sep = ""
        if prev is not None and grouped and prev[0] != keys[0] and lay.group_sep != "none":
            sep = lay.group_sep
        body.append(cells)
        seps.append(sep)
        prev = keys
    return Grid(align, header, body, seps, nk)


def _x_decimals(t: Table) -> int:
    if not t.x_metric:
        return 2
    from .table import auto_decimals
    vals = [r[t.row_keys.index(X_VALUE)] for r in t.rows if X_VALUE in t.row_keys]
    return auto_decimals([v for v in vals if v is not None])


# ---------------------------------------------------------------- LaTeX --
def colspec(align: list[str]) -> str:
    """'r *{5}{c}': runs of more than two equal columns are compressed."""
    parts, i = [], 0
    while i < len(align):
        j = i
        while j < len(align) and align[j] == align[i]:
            j += 1
        n = j - i
        parts.append(f"*{{{n}}}{{{align[i]}}}" if n > 2 else " ".join(align[i] * n))
        i = j
    return " ".join(parts)


def caption_text(t: Table, ts: TableSpec, out) -> str:
    """User caption (LaTeX, as typed) + automatic sentences (escaped)."""
    o, fm = ts.output, ts.format
    parts = [o.caption.strip()] if o.caption.strip() else []
    if o.caption_auto:
        auto = []
        if fm.stat_place in ("caption", "both") or fm.n_mode == "caption":
            n = t.n_text if fm.n_mode == "caption" else ""
            if fm.stat_place in ("caption", "both"):
                auto.append(t.stat.sentence(n))
            elif n:
                auto.append(f"Each value is over {n}." if not t.stat.per_trial
                            else f"Per-trial values over {n}.")
        if o.caption_detail and t.detail:
            auto.append(t.detail)
        if any(c.best for c in t.cells.values()):
            auto.append("The best value " + ("in each group " if fm.best_scope == "group"
                                              else "") + "is in bold.")
        auto_s = " ".join(auto)
        if auto_s:
            parts.append(out.esc(auto_s) if out.kind == "tex" else out.esc(auto_s))
    return " ".join(parts) or ("Caption." if out.kind == "tex" else "")


def safe_label(s: str) -> str:
    return re.sub(r"[^\w\-:.]+", "-", s.strip()).strip("-") or "table"


def to_latex(t: Table, ts: TableSpec) -> str:
    out = TexOut(ts.format.math_minus)
    g = build_grid(t, ts, out)
    o = ts.output
    I1, I2 = "\t", "\t\t"
    lines = [rf"\begin{{table}}[{o.placement or 'ht'}]", I1 + r"\centering"]
    if o.font_size and o.font_size != "normalsize":
        lines.append(I1 + "\\" + o.font_size)
    if o.tabcolsep is not None:
        lines.append(I1 + rf"\setlength{{\tabcolsep}}{{{o.tabcolsep:g}pt}}")
    lines.append(I1 + rf"\caption{{{caption_text(t, ts, out)}}}")
    label = o.label or ("tab:" + safe_label(o.filename or "table"))
    lines.append(I1 + rf"\label{{{label}}}")
    if o.resize:
        lines.append(I1 + r"\resizebox{\textwidth}{!}{%")
    lines.append(I1 + rf"\begin{{tabular}}{{{colspec(g.align)}}}")
    lines.append(I2 + r"\toprule")
    for row in g.header:
        cells, col, rules = [], 1, []
        for h in row:
            if h.span > 1:
                cells.append(rf"\multicolumn{{{h.span}}}{{c}}{{{h.text}}}")
            else:
                cells.append(h.text)
            if h.rule and h.text:
                rules.append(rf"\cmidrule(lr){{{col}-{col + h.span - 1}}}")
            col += h.span
        lines.append(I2 + _join_cells(cells) + r" \\")
        if rules:
            lines.append(I2 + " ".join(rules))
    lines.append(I2 + r"\midrule")
    for cells, sep in zip(g.body, g.seps):
        if sep == "space":
            lines.append(I2 + r"\addlinespace")
        elif sep == "midrule":
            lines.append(I2 + r"\midrule")
        lines.append(I2 + _join_cells(cells) + r" \\")
    lines.append(I2 + r"\bottomrule")
    lines.append(I1 + r"\end{tabular}" + ("}" if o.resize else ""))
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def _join_cells(cells: list[str]) -> str:
    return " & ".join(cells)


# ----------------------------------------------------------------- HTML --
PREVIEW_CSS = """
.rt-wrap {font-family: 'TeX Gyre Termes', 'Times New Roman', Times, serif; color: #111;
          background: #fff; padding: 14px 18px; border-radius: 6px; overflow-x: auto;}
.rt-cap {font-size: 13px; margin: 0 auto 8px auto; max-width: 18cm; line-height: 1.35;}
.rt-cap b {font-weight: 600;}
table.rt {border-collapse: collapse; margin: 0 auto; font-size: 14px;}
table.rt.small {font-size: 13px;} table.rt.footnotesize {font-size: 12px;}
table.rt.scriptsize {font-size: 10.5px;}
table.rt td, table.rt th {padding: 2px 8px; white-space: nowrap; font-weight: normal;
          vertical-align: bottom;}
table.rt thead tr:first-child th {border-top: 1.6px solid #000; padding-top: 5px;}
table.rt thead tr:last-child th {border-bottom: 1px solid #000; padding-bottom: 4px;}
table.rt tbody tr:last-child td {border-bottom: 1.6px solid #000; padding-bottom: 5px;}
table.rt th.rule {box-shadow: inset 0 -0.6px 0 0 #000;}
table.rt tr.space td {padding-top: 7px;}
table.rt tr.midrule td {border-top: 0.6px solid #000;}
table.rt .l {text-align: left;} table.rt .r {text-align: right;} table.rt .c {text-align: center;}
table.rt .stat {font-size: 0.8em; color: #333;}
table.rt .sm {font-size: 0.8em;}
"""


def to_html(t: Table, ts: TableSpec) -> str:
    out = HtmlOut()
    g = build_grid(t, ts, out)
    rows = []
    for row in g.header:
        col, ths = 0, []
        for h in row:
            a = g.align[col] if h.span == 1 else "c"
            cls = f"{a}{' rule' if h.rule and h.text else ''}"
            ths.append(f'<th class="{cls}" colspan="{h.span}">{h.text}</th>')
            col += h.span
        rows.append("<tr>" + "".join(ths) + "</tr>")
    head = "<thead>" + "".join(rows) + "</thead>"
    brows = []
    for cells, sep in zip(g.body, g.seps):
        tds = "".join(f'<td class="{a}">{c}</td>' for a, c in zip(g.align, cells))
        brows.append(f'<tr class="{sep}">{tds}</tr>')
    body = "<tbody>" + "".join(brows) + "</tbody>"
    cap = caption_text(t, ts, out)
    label = ts.output.label or ("tab:" + safe_label(ts.output.filename or "table"))
    return (f'<div class="rt-wrap"><div class="rt-cap"><b>Table:</b> {cap} '
            f'<span style="color:#888">[{html.escape(label)}]</span></div>'
            f'<table class="rt {ts.output.font_size}">{head}{body}</table></div>')


# ------------------------------------------------------------------ CSV --
def to_frame(t: Table, ts: TableSpec) -> pd.DataFrame:
    """Tidy numbers behind the table (one row per cell) plus the formatted text."""
    out = HtmlOut()
    recs = []
    for (r, c), cell in sorted(t.cells.items()):
        rec = {}
        for k, v in zip(t.row_keys, t.rows[r]):
            rec[key_label(k, t.plot, x_metric=t.x_metric)] = v
        for k, v in zip(t.col_keys, t.cols[c]):
            rec[key_label(k, t.plot, x_metric=t.x_metric)] = v
        centre, sp = cell_parts(cell, t, ts, out)
        rec.update({"metric": cell.metric, "statistic": t.stat.func,
                    "spread": t.stat.spread, "value": cell.value, "lo": cell.lo,
                    "hi": cell.hi, "n": cell.n,
                    "as_percent": t.percent.get(cell.metric, False),
                    "text": re.sub(r"<[^>]+>", "", f"{centre} {sp}".strip())})
        recs.append(rec)
    return pd.DataFrame(recs)
