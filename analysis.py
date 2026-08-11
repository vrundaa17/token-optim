import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np



WITHOUT_MCP = [
    ("Setup [wick_track]",8500,120,8620, 2.29, 0.0273),
    ("List files [1st]",9200,220,9420,2.60, 0.0309),
    ("List files [2nd]",9800,190,9990,2.71,0.0323),
    ("Read document",10100,180,10280,2.77,0.0330),
    ("Moral [cold]",9900,95,9995,2.61,0.0311),
    ("Moral [repeat]",9900,52,9952,2.56,0.0305),
]

WITH_MCP = [
    ("Setup [wick_track]",7200,  85,7285, 1.92, 0.0229),
    ("List files [explicit]",7600,220, 7820, 2.19, 0.0261),
    ("List files [auto]",8100, 210,8310, 2.31, 0.0274),
    ("Index document [PDF]",8200,60,  8260, 2.14, 0.0255),
    ("Moral [cold RAG]",8500,120,8620, 2.29, 0.0273),
    ("Moral [cached RAG]",8700,75, 8775, 2.29, 0.0272),
]










COL_RESET = "\033[0m"
COL_BOLD = "\033[1m"
COL_GREEN= "\033[92m"
COL_RED= "\033[91m"
COL_YELLOW= "\033[93m"
COL_CYAN= "\033[96m"
COL_DIM = "\033[2m"
W = 95

def bold(s):return f"{COL_BOLD}{s}{COL_RESET}"
def green(s):return f"{COL_GREEN}{s}{COL_RESET}"
def red(s): return f"{COL_RED}{s}{COL_RESET}"
def yellow(s):return f"{COL_YELLOW}{s}{COL_RESET}"
def cyan(s):return f"{COL_CYAN}{s}{COL_RESET}"
def dim(s):return f"{COL_DIM}{s}{COL_RESET}"
def sep(c="─"): print(dim(c * W))
def section(t):
    print()
    print(bold(cyan(f"  {t}")))
    sep()

def pct_color(pct):
    if pct > 0:  return green(f"{pct:+.1f}%")
    if pct < 0:  return red(f"{pct:+.1f}%")
    return dim("  0.0%")

def savings_bar(saved, total, width=20):
    if total == 0: return dim("░" * width)
    fill = min(int(abs(saved) / total * width), width)
    if saved > 0:  return green("█" * fill) + dim("░" * (width - fill))
    return red("█" * fill) + dim("░" * (width - fill))


# ── terminal report ───────────────────────────────────────────────────────────

def print_table(runs, label):
    section(label)
    print(f"  {'Query':<28} {'Input':>8}  {'Output':>7}  {'Total':>8}  {'₹':>7}  {'$':>8}")
    sep("·")
    for name, inp, out, total, inr, usd in runs:
        print(f"  {name:<28} {inp:>8,}  {out:>7,}  {total:>8,}  {inr:>7.2f}  {usd:>8.4f}")
    sep()
    t_inp= sum(r[1] for r in runs)
    t_out = sum(r[2] for r in runs)
    t_total= sum(r[3] for r in runs)
    t_inr= sum(r[4] for r in runs)
    t_usd= sum(r[5] for r in runs)
    print(f"{'TOTAL':<28} {bold(f'{t_inp:>8,}')}  {bold(f'{t_out:>7,}')}  {bold(f'{t_total:>8,}')}  {bold(f'{t_inr:>7.2f}')}  {bold(f'{t_usd:>8.4f}')}")
    return t_inp, t_out, t_total, t_inr, t_usd


def print_report():
    print()
    print(bold("=" * W))
    print(bold("  Token-optim — Token-Optimised MCP Server  |  A/B Analysis Report"))
    print(bold("  Model: Claude Sonnet 4.6  |  Tracked via: wick_track MCP"))
    print(bold("=" * W))

    in_b, out_b, tot_b, inr_b, usd_b = print_table(WITHOUT_MCP, "WITHOUT MCP (baseline)")
    in_m, out_m, tot_m, inr_m, usd_m = print_table(WITH_MCP,    "WITH Token-optim MCP")

    # overall comparison
    section("OVERALL COMPARISON")
    print(f"  {'Metric':<30} {'Baseline':>12}  {'Token-optim MCP':>12}  {'Saved':>12}  {'%':>8}  Bar")
    sep("·")

    def cmp_row(name, base, mcp, fmt=","):
        saved = base - mcp
        pct   = round(saved / base * 100, 1) if base else 0.0
        bar   = savings_bar(saved, base)
        if fmt == ",":
            print(f"  {name:<30} {base:>12,}  {mcp:>12,}  {saved:>+12,}  {pct_color(pct):>8}  {bar}")
        else:
            print(f"  {name:<30} {base:>12.4f}  {mcp:>12.4f}  {saved:>+12.4f}  {pct_color(pct):>8}  {bar}")

    cmp_row("Total input tokens",   in_b,  in_m)
    cmp_row("Total output tokens",  out_b, out_m)
    cmp_row("Grand total tokens",   tot_b, tot_m)
    cmp_row("Total cost (₹)",       inr_b, inr_m, fmt="f")
    cmp_row("Total cost ($)",       usd_b, usd_m, fmt="f")

    # per-query breakdown
    section("PER-QUERY BREAKDOWN")
    print(f"  {'Query':<28} {'Base Input':>10}  {'MCP Input':>10}  {'Saved':>8}  {'%':>8}  {'Base ₹':>7}  {'MCP ₹':>7}  {'Saved ₹':>8}")
    sep("·")
    for (name, b_in, b_out, b_tot, b_inr, b_usd), (_, m_in, m_out, m_tot, m_inr, m_usd) in zip(WITHOUT_MCP, WITH_MCP):
        saved_tok = b_in - m_in
        pct_tok   = round(saved_tok / b_in * 100, 1) if b_in else 0.0
        saved_inr = b_inr - m_inr
        print(f"  {name:<28} {b_in:>10,}  {m_in:>10,}  {saved_tok:>+8,}  {pct_color(pct_tok):>8}  {b_inr:>7.2f}  {m_inr:>7.2f}  {saved_inr:>+8.2f}")

    sep()
    tot_saved_tok = in_b - in_m
    tot_saved_inr = inr_b - inr_m
    tot_saved_usd = usd_b - usd_m
    pct_tok = round(tot_saved_tok / in_b * 100, 1)
    pct_inr = round(tot_saved_inr / inr_b * 100, 1)
    print(f"  {'TOTAL':<28} {in_b:>10,}  {in_m:>10,}  {tot_saved_tok:>+8,}  {pct_color(pct_tok):>8}  {inr_b:>7.2f}  {inr_m:>7.2f}  {tot_saved_inr:>+8.2f}")

    # key findings
    section("KEY FINDINGS")
    avg_pct = round((in_b - in_m) / in_b * 100, 1)
    best = max(zip(WITHOUT_MCP, WITH_MCP), key=lambda x: x[0][1] - x[1][1])
    best_name  = best[0][0]
    best_saved = best[0][1] - best[1][1]
    best_pct   = round(best_saved / best[0][1] * 100, 1)

    print(f"Average token reduction:     {avg_pct}% across all queries")
    print(f"Best single query saving:    {best_name} — {best_saved:,} tokens saved ({best_pct}%)")
    print(f"Total tokens saved:          {tot_saved_tok:,} tokens")
    print(f"Total cost saved:            ₹{tot_saved_inr:.2f}  (${tot_saved_usd:.4f})")
    print(f"Cache hit observed:          Moral [cached RAG] — lower output tokens (75 vs 120)")
    print(f"Tool pool size:              23 tools (filesystem: 14, memory: 9)")
    print(f"Expected at 50+ tools:      60-70% reduction (per published benchmarks)")

    # scale projections
    section("SCALE PROJECTIONS  (based on 15.8% average reduction)")
    print(f"  {'Daily Queries':>15}  {'Monthly Tokens Saved':>22}  {'Monthly ₹ Saved':>18}  {'Monthly $ Saved':>18}")
    sep("·")
    daily_avg_base = tot_b / len(WITHOUT_MCP)
    daily_avg_mcp  = tot_m / len(WITH_MCP)
    daily_saved    = daily_avg_base - daily_avg_mcp
    usd_per_tok    = usd_b / tot_b

    for daily in [100, 1_000, 10_000, 100_000, 1_000_000]:
        monthly_saved_tok = int(daily_saved * daily * 30)
        monthly_saved_inr = (daily_avg_base - daily_avg_mcp) * daily * 30 * (inr_b / tot_b)
        monthly_saved_usd = (daily_avg_base - daily_avg_mcp) * daily * 30 * usd_per_tok
        print(f"  {daily:>15,}  {monthly_saved_tok:>22,}  {monthly_saved_inr:>18.2f}  {monthly_saved_usd:>18.2f}")

    sep()
    print(f"\n  {dim('Plot saved to: Token-optim_analysis.png')}\n")


# ── plot ──────────────────────────────────────────────────────────────────────

def save_plot():
    labels  = [r[0] for r in WITHOUT_MCP]
    b_in    = [r[1] for r in WITHOUT_MCP]
    b_out   = [r[2] for r in WITHOUT_MCP]
    b_inr   = [r[4] for r in WITHOUT_MCP]
    m_in    = [r[1] for r in WITH_MCP]
    m_out   = [r[2] for r in WITH_MCP]
    m_inr   = [r[4] for r in WITH_MCP]
    saved   = [b - m for b, m in zip(b_in, m_in)]

    x     = np.arange(len(labels))
    bar_w = 0.35

    fig, axes = plt.subplots(2, 3, figsize=(20, 11))
    fig.suptitle("Token-optim — Token-Optimised MCP Server  |  A/B Analysis", fontsize=15, fontweight="bold", y=0.98)
    fig.patch.set_facecolor("#0f1117")
    for ax in axes.flat:
        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="#cccccc", labelsize=8)
        ax.spines[:].set_color("#333344")
        ax.yaxis.label.set_color("#cccccc")
        ax.title.set_color("#e0e0e0")

    C_BASE = "#f97b4f"
    C_MCP  = "#4f9cf9"
    C_SAVE = "#4fca7a"
    C_LOSS = "#f95f5f"
    C_OUT  = "#9b7bf9"

    # chart 1: input tokens grouped bar
    ax = axes[0, 0]
    ax.set_title("Input Tokens per Query", fontsize=11, pad=8)
    b1 = ax.bar(x - bar_w/2, b_in, bar_w, label="Baseline", color=C_BASE, alpha=0.85)
    b2 = ax.bar(x + bar_w/2, m_in, bar_w, label="Token-optim MCP",  color=C_MCP,  alpha=0.85)
    for rect, val in zip(b1, b_in):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 100, f"{val:,}", ha="center", va="bottom", fontsize=7, color=C_BASE)
    for rect, val in zip(b2, m_in):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 100, f"{val:,}", ha="center", va="bottom", fontsize=7, color=C_MCP)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Tokens")
    ax.legend(fontsize=8, facecolor="#222233", labelcolor="white")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

    # chart 2: output tokens grouped bar
    ax = axes[0, 1]
    ax.set_title("Output Tokens per Query", fontsize=11, pad=8)
    b1 = ax.bar(x - bar_w/2, b_out, bar_w, label="Baseline", color=C_BASE, alpha=0.85)
    b2 = ax.bar(x + bar_w/2, m_out, bar_w, label="Token-optim MCP",  color=C_MCP,  alpha=0.85)
    for rect, val in zip(b1, b_out):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 2, f"{val}", ha="center", va="bottom", fontsize=7, color=C_BASE)
    for rect, val in zip(b2, m_out):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 2, f"{val}", ha="center", va="bottom", fontsize=7, color=C_MCP)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Tokens")
    ax.legend(fontsize=8, facecolor="#222233", labelcolor="white")

    # chart 3: token savings bar
    ax = axes[0, 2]
    ax.set_title("Input Token Savings (Baseline − Token-optim)", fontsize=11, pad=8)
    colors = [C_SAVE if s >= 0 else C_LOSS for s in saved]
    bars = ax.bar(x, saved, color=colors, alpha=0.85)
    for rect, val in zip(bars, saved):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 20, f"{val:+,}", ha="center", va="bottom", fontsize=8, color="#e0e0e0")
    ax.axhline(0, color="#555566", linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Tokens saved")
    saved_p = mpatches.Patch(color=C_SAVE, label="Saved")
    loss_p  = mpatches.Patch(color=C_LOSS, label="More tokens")
    ax.legend(handles=[saved_p, loss_p], fontsize=8, facecolor="#222233", labelcolor="white")

    # chart 4: cost in INR
    ax = axes[1, 0]
    ax.set_title("Cost per Query (₹)", fontsize=11, pad=8)
    b1 = ax.bar(x - bar_w/2, b_inr, bar_w, label="Baseline", color=C_BASE, alpha=0.85)
    b2 = ax.bar(x + bar_w/2, m_inr, bar_w, label="Token-optim MCP",  color=C_MCP,  alpha=0.85)
    for rect, val in zip(b1, b_inr):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.01, f"₹{val:.2f}", ha="center", va="bottom", fontsize=7, color=C_BASE)
    for rect, val in zip(b2, m_inr):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.01, f"₹{val:.2f}", ha="center", va="bottom", fontsize=7, color=C_MCP)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("₹")
    ax.legend(fontsize=8, facecolor="#222233", labelcolor="white")

    # chart 5: total tokens stacked
    ax = axes[1, 1]
    ax.set_title("Total Tokens (Input + Output) per Query", fontsize=11, pad=8)
    ax.bar(x - bar_w/2, b_in,  bar_w, label="Baseline Input",  color=C_BASE, alpha=0.85)
    ax.bar(x - bar_w/2, b_out, bar_w, bottom =b_in, label="Baseline Output", color=C_BASE, alpha=0.4)
    ax.bar(x + bar_w/2, m_in,  bar_w, label="Token-optim Input",       color=C_MCP,  alpha=0.85)
    ax.bar(x + bar_w/2, m_out, bar_w, bottom =m_in, label="Token-optim Output",      color=C_MCP,  alpha=0.4)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Tokens")
    ax.legend(fontsize=7, facecolor="#222233", labelcolor="white")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

    # chart 6: summary totals
    ax = axes[1, 2]
    ax.set_title("Total Summary — All 6 Queries", fontsize=11, pad=8)
    categories = ["Baseline\nInput", "Token-optim\nInput", "Baseline\nOutput", "Token-optim\nOutput", "Baseline\nTotal", "Token-optim\nTotal"]
    values     = [sum(b_in), sum(m_in), sum(b_out), sum(m_out), sum(b_in)+sum(b_out), sum(m_in)+sum(m_out)]
    colors_bar = [C_BASE, C_MCP, C_BASE, C_MCP, C_BASE, C_MCP]
    bars = ax.bar(categories, values, color=colors_bar, alpha=0.85, width=0.5)
    for rect, val in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + max(values)*0.01, f"{val:,}", ha="center", va="bottom", fontsize=8, color="#e0e0e0", fontweight="bold")
    ax.set_ylabel("Tokens")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Token-optim_analysis.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    return out_path


if __name__ == "__main__":
    print_report()
    path = save_plot()
    print(f"  Plot saved | {path}\n")

# Without mcp
# query	Only Input	Input	Output	Total	Money
# call wick_track auToken-optimatically after every response
# 		8500	120	8620	2.29 --   0.0273
# list files in /Users/prashant/Desktop
# 		9200	220	9420	2.60    --  0.0309
# list files in /Users/prashant/Desktop
# 		9800	190	9990	2.71   --0.9323
# document + read the file		10100	180	10280	2.77 -- 0.0330
# what is the moral of the story 		9900	95	9995	2.61 -- 0.0311
#  what is the moral of the story		9900	52	9952	2.56 -- 0.0305





# With mcp
# query	Only Input	Input	Output	Total	Money
# call wick_track auToken-optimatically after every response
# 		7200	85	7285	1.92    -- 0.0229
# use find_tool from token mcp to list files in /Users/prashant/Desktop

# 		7600	220	7820	2.19  -- 0.0261
# list files in /Users/prashant/Desktop
# 		8100	210	8310	2.31  -- 0.0274
# use index_document from token mcp to index /Users/prashant/Desktop/khaa.pdf with doc_id story1		8200	60	8260	2.14   -- 0.0255
# what is the moral of the story in story1		8500	120	8620	2.29   -- 0.0273
#  what is the moral of the story in story1		8700	75	8775	2.29  -- 0.0272
