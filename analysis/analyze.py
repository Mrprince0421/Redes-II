#!/usr/bin/env python3
"""
Análise Comparativa TCP vs R-UDP
Autor: Marcos Eduardo Barbosa Pachêco
Matrícula: 20199017697
"""

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os
import sys
import argparse

# ── Paleta de cores ──────────────────────────────────────────────────────────
COLOR_TCP  = "#2196F3"
COLOR_RUDP = "#F44336"
SCENARIOS  = {"A": "0% perda / 10ms", "B": "5% perda / 50ms", "C": "10% perda / 100ms"}
OUT_DIR    = "analysis"
os.makedirs(OUT_DIR, exist_ok=True)


def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    df["throughput_kbps"] = pd.to_numeric(df["throughput_kbps"], errors="coerce")
    df["elapsed_s"]       = pd.to_numeric(df["elapsed_s"],       errors="coerce")
    df.dropna(subset=["throughput_kbps", "elapsed_s"], inplace=True)
    return df


def print_stats(df: pd.DataFrame):
    print("\n" + "="*70)
    print("ESTATÍSTICAS DE VAZÃO (KB/s)")
    print("="*70)
    summary = (df.groupby(["mode", "scenario"])["throughput_kbps"]
                 .agg(["min", "mean", "max", "std", "count"])
                 .round(3))
    summary.columns = ["Mín", "Média", "Máx", "Desvio Padrão", "N"]
    print(summary.to_string())
    print()

    print("="*70)
    print("ESTATÍSTICAS DE TEMPO (s)")
    print("="*70)
    summary2 = (df.groupby(["mode", "scenario"])["elapsed_s"]
                  .agg(["min", "mean", "max", "std"])
                  .round(4))
    summary2.columns = ["Mín", "Média", "Máx", "Desvio Padrão"]
    print(summary2.to_string())

    if "retransmissions" in df.columns:
        print("\n" + "="*70)
        print("RETRANSMISSÕES (R-UDP)")
        print("="*70)
        rudp = df[df["mode"] == "RUDP"]
        if not rudp.empty:
            r = (rudp.groupby("scenario")["retransmissions"]
                     .agg(["sum", "mean", "max"])
                     .round(2))
            r.columns = ["Total", "Média", "Máx"]
            print(r.to_string())


# ── Gráfico 1: Barras com erro (throughput por cenário) ──────────────────────

def plot_bar_throughput(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    fig.suptitle("Vazão Média por Cenário – TCP vs R-UDP\n"
                 "Marcos Eduardo Barbosa Pachêco | 20199017697",
                 fontsize=13, fontweight="bold")

    for i, (sc, sc_label) in enumerate(SCENARIOS.items()):
        ax = axes[i]
        sub = df[df["scenario"] == sc]
        modes  = ["TCP", "RUDP"]
        means  = []
        stds   = []
        colors = [COLOR_TCP, COLOR_RUDP]
        for m in modes:
            s = sub[sub["mode"] == m]["throughput_kbps"]
            means.append(s.mean() if not s.empty else 0)
            stds.append(s.std()  if not s.empty else 0)

        x = np.arange(len(modes))
        bars = ax.bar(x, means, yerr=stds, capsize=6,
                      color=colors, edgecolor="white", width=0.5,
                      error_kw={"elinewidth": 2, "ecolor": "black"})
        ax.set_title(f"Cenário {sc}\n{sc_label}", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(modes)
        ax.set_ylabel("Vazão (KB/s)")
        ax.set_xlabel("Protocolo")
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        for bar, mean in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{mean:.1f}", ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "fig1_bar_throughput.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[✓] Salvo: {path}")


# ── Gráfico 2: Boxplot de throughput ─────────────────────────────────────────

def plot_boxplot(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    fig.suptitle("Distribuição da Vazão – TCP vs R-UDP\n"
                 "Marcos Eduardo Barbosa Pachêco | 20199017697",
                 fontsize=13, fontweight="bold")

    for i, (sc, sc_label) in enumerate(SCENARIOS.items()):
        ax = axes[i]
        sub = df[df["scenario"] == sc]
        data_tcp  = sub[sub["mode"] == "TCP"]["throughput_kbps"].dropna().tolist()
        data_rudp = sub[sub["mode"] == "RUDP"]["throughput_kbps"].dropna().tolist()

        bp = ax.boxplot([data_tcp, data_rudp],
                        tick_labels=["TCP", "R-UDP"],
                        patch_artist=True,
                        medianprops={"color": "black", "linewidth": 2})
        bp["boxes"][0].set_facecolor(COLOR_TCP  + "99")
        if len(bp["boxes"]) > 1:
            bp["boxes"][1].set_facecolor(COLOR_RUDP + "99")

        ax.set_title(f"Cenário {sc}\n{sc_label}", fontsize=10)
        ax.set_ylabel("Vazão (KB/s)")
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "fig2_boxplot.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[✓] Salvo: {path}")


# ── Gráfico 3: Linha de throughput ao longo das execuções ────────────────────

def plot_throughput_over_runs(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    fig.suptitle("Vazão por Execução – TCP vs R-UDP\n"
                 "Marcos Eduardo Barbosa Pachêco | 20199017697",
                 fontsize=13, fontweight="bold")

    for i, (sc, sc_label) in enumerate(SCENARIOS.items()):
        ax = axes[i]
        sub = df[df["scenario"] == sc].copy()
        for mode, color in [("TCP", COLOR_TCP), ("RUDP", COLOR_RUDP)]:
            mdf = sub[sub["mode"] == mode].reset_index(drop=True)
            if not mdf.empty:
                ax.plot(mdf.index + 1, mdf["throughput_kbps"],
                        marker="o", label=mode, color=color, linewidth=1.5, markersize=4)

        ax.set_title(f"Cenário {sc}\n{sc_label}", fontsize=10)
        ax.set_xlabel("Execução")
        ax.set_ylabel("Vazão (KB/s)")
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.4)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "fig3_runs.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[✓] Salvo: {path}")


# ── Gráfico 4: Retransmissões R-UDP por cenário ───────────────────────────────

def plot_retransmissions(df: pd.DataFrame):
    if "retransmissions" not in df.columns:
        return
    rudp = df[df["mode"] == "RUDP"]
    if rudp.empty:
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.suptitle("Retransmissões R-UDP por Cenário\n"
                 "Marcos Eduardo Barbosa Pachêco | 20199017697",
                 fontsize=12, fontweight="bold")

    sc_list = sorted(rudp["scenario"].unique())
    means   = [rudp[rudp["scenario"] == s]["retransmissions"].mean() for s in sc_list]
    stds    = [rudp[rudp["scenario"] == s]["retransmissions"].std()  for s in sc_list]
    labels  = [f"Cenário {s}\n{SCENARIOS.get(s,'')}" for s in sc_list]

    x = np.arange(len(sc_list))
    ax.bar(x, means, yerr=stds, capsize=6, color=COLOR_RUDP,
           edgecolor="white", width=0.5,
           error_kw={"elinewidth": 2})
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Retransmissões (média)")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "fig4_retransmissions.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[✓] Salvo: {path}")


# ── Gráfico 5: Tempo médio de transferência ───────────────────────────────────

def plot_elapsed(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Tempo Médio de Transferência – TCP vs R-UDP\n"
                 "Marcos Eduardo Barbosa Pachêco | 20199017697",
                 fontsize=13, fontweight="bold")

    for i, (sc, sc_label) in enumerate(SCENARIOS.items()):
        ax = axes[i]
        sub = df[df["scenario"] == sc]
        modes  = ["TCP", "RUDP"]
        means  = []
        stds   = []
        for m in modes:
            s = sub[sub["mode"] == m]["elapsed_s"]
            means.append(s.mean() if not s.empty else 0)
            stds.append(s.std()   if not s.empty else 0)

        x = np.arange(len(modes))
        ax.bar(x, means, yerr=stds, capsize=6,
               color=[COLOR_TCP, COLOR_RUDP], edgecolor="white", width=0.5,
               error_kw={"elinewidth": 2, "ecolor": "black"})
        ax.set_title(f"Cenário {sc}\n{sc_label}", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(modes)
        ax.set_ylabel("Tempo (s)")
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, "fig5_elapsed.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[✓] Salvo: {path}")


# ── Exportar tabela resumo ────────────────────────────────────────────────────

def export_summary(df: pd.DataFrame):
    summary = (df.groupby(["mode", "scenario"])["throughput_kbps"]
                 .agg(min="min", mean="mean", max="max", std="std", n="count")
                 .round(3)
                 .reset_index())
    path = os.path.join(OUT_DIR, "summary_stats.csv")
    summary.to_csv(path, index=False)
    print(f"[✓] Salvo: {path}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Análise Estatística TCP vs R-UDP")
    parser.add_argument("csv", nargs="?", default="logs/results.csv",
                        help="Arquivo CSV de resultados")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[ERRO] Arquivo não encontrado: {args.csv}")
        print("Gerando dados simulados para demonstração…")

        # Gerar dados simulados realistas para demonstração
        import random
        random.seed(42)
        rows = []
        for mode in ["TCP", "RUDP"]:
            for sc in ["A", "B", "C"]:
                loss   = {"A": 0.00, "B": 0.05, "C": 0.10}[sc]
                delay  = {"A": 0.01, "B": 0.05, "C": 0.10}[sc]
                base_tp = {"TCP": 9000, "RUDP": 6500}[mode]
                for _ in range(20):
                    noise   = random.gauss(0, base_tp * 0.08)
                    penalty = base_tp * (loss * 4 + delay * 15)
                    tp      = max(100, base_tp - penalty + noise)
                    elapsed = (1024 * 1024) / (tp * 1024)   # ~1 MB file
                    retx    = int(random.gauss(loss * 40, loss * 15)) if mode == "RUDP" else 0
                    rows.append({
                        "mode":            mode,
                        "scenario":        sc,
                        "filesize_bytes":  1048576,
                        "elapsed_s":       round(elapsed, 6),
                        "throughput_kbps": round(tp, 3),
                        "retransmissions": max(0, retx),
                        "timestamp":       "2026-05-20T10:00:00"
                    })
        os.makedirs("logs", exist_ok=True)
        pd.DataFrame(rows).to_csv(args.csv, index=False)
        print(f"[✓] Dados simulados salvos em: {args.csv}")

    df = load_data(args.csv)
    print(f"\nTotal de registros carregados: {len(df)}")
    print(df.groupby(["mode", "scenario"]).size().to_string())

    print_stats(df)
    plot_bar_throughput(df)
    plot_boxplot(df)
    plot_throughput_over_runs(df)
    plot_retransmissions(df)
    plot_elapsed(df)
    export_summary(df)

    print("\n[✓] Análise concluída. Gráficos salvos em ./analysis/")
