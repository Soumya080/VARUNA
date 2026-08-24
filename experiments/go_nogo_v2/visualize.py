"""
VARUNA GRID — Visualisation routines for Go/No-Go v2.
Generates matplotlib plots from sweep results.
"""
import json
import os
import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def plot_results(results_dir: str = "results_v2"):
    """Generate all plots from a completed sweep."""
    if not HAS_MPL:
        print("matplotlib not installed — skipping visualisation.")
        return

    results_path = os.path.join(results_dir, "results.json")
    metrics_path = os.path.join(results_dir, "metrics.json")

    if not os.path.exists(results_path):
        print(f"No results found at {results_path}")
        return

    with open(results_path) as f:
        results = json.load(f)
    with open(metrics_path) as f:
        metrics = json.load(f)

    os.makedirs(os.path.join(results_dir, "figures"), exist_ok=True)

    _plot_posterior_heatmap(results, results_dir)
    _plot_entropy_distribution(results, results_dir)
    _plot_accuracy_by_age(results, results_dir)
    _plot_decision_pie(metrics, results_dir)
    _plot_gate_pie(metrics, results_dir)
    _plot_latent_vs_known(results, results_dir)

    print(f"Figures saved to {os.path.join(results_dir, 'figures')}/")


def _plot_posterior_heatmap(results, results_dir):
    """Per-case posterior for true source vs predicted source."""
    true_probs = []
    pred_probs = []
    labels = []

    for r in results:
        true_mmsi = r["true_mmsi"]
        pred_mmsi = r["pred_mmsi"]
        posterior = r["posterior"]

        true_probs.append(posterior.get(true_mmsi, 0.0))
        pred_probs.append(posterior.get(pred_mmsi, 0.0))
        labels.append("correct" if r["is_correct"] else "wrong")

    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#2ecc71" if l == "correct" else "#e74c3c" for l in labels]
    ax.scatter(true_probs, pred_probs, c=colors, alpha=0.7, edgecolors="k", s=60)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="identity")
    ax.set_xlabel("P(true source)")
    ax.set_ylabel("P(predicted source)")
    ax.set_title("Posterior: True vs Predicted Source")
    ax.legend(["identity", "correct", "wrong"])
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "posterior_scatter.png"), dpi=150)
    plt.close(fig)


def _plot_entropy_distribution(results, results_dir):
    """Histogram of posterior entropy."""
    entropies = [r["entropy"] for r in results]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(entropies, bins=20, color="#3498db", edgecolor="k", alpha=0.8)
    ax.axvline(0.9, color="red", linestyle="--", label="gate threshold")
    ax.set_xlabel("Posterior Entropy")
    ax.set_ylabel("Count")
    ax.set_title("Distribution of Posterior Entropy")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "entropy_hist.png"), dpi=150)
    plt.close(fig)


def _plot_accuracy_by_age(results, results_dir):
    """Accuracy binned by true slick age."""
    ages = [r.get("true_age_hours", 0) for r in results]
    correct = [1 if r["is_correct"] else 0 for r in results]

    if not any(ages):
        return

    age_bins = np.arange(0, max(ages) + 12, 12)
    bin_indices = np.digitize(ages, age_bins)

    bin_acc = []
    bin_labels = []
    for i in range(1, len(age_bins)):
        mask = [j for j, b in enumerate(bin_indices) if b == i]
        if mask:
            acc = np.mean([correct[j] for j in mask])
            bin_acc.append(acc)
            bin_labels.append(f"{age_bins[i-1]:.0f}-{age_bins[i]:.0f}h")

    if not bin_acc:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(range(len(bin_acc)), bin_acc, color="#9b59b6", edgecolor="k")
    ax.set_xticks(range(len(bin_labels)))
    ax.set_xticklabels(bin_labels, rotation=45)
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy by Slick Age")
    ax.set_ylim(0, 1.05)
    ax.axhline(1.0 / 5, color="gray", linestyle=":", label="random baseline (1/5)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "accuracy_by_age.png"), dpi=150)
    plt.close(fig)


def _plot_decision_pie(metrics, results_dir):
    """Pie chart of decision states."""
    decisions = metrics.get("decisions", {})
    if not decisions:
        return

    labels = list(decisions.keys())
    sizes = list(decisions.values())
    colors = ["#2ecc71", "#f39c12", "#e74c3c", "#3498db", "#95a5a6"]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(sizes, labels=labels, autopct="%1.0f%%", colors=colors[:len(labels)],
           startangle=90, textprops={"fontsize": 9})
    ax.set_title("Decision State Distribution")
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "decision_pie.png"), dpi=150)
    plt.close(fig)


def _plot_gate_pie(metrics, results_dir):
    """Pie chart of validity gate states."""
    gates = metrics.get("gate_states", {})
    if not gates:
        return

    labels = list(gates.keys())
    sizes = list(gates.values())
    colors = ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(sizes, labels=labels, autopct="%1.0f%%", colors=colors[:len(labels)],
           startangle=90, textprops={"fontsize": 9})
    ax.set_title("Validity Gate Distribution")
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "gate_pie.png"), dpi=150)
    plt.close(fig)


def _plot_latent_vs_known(results, results_dir):
    """Box plot comparing latent probability for latent vs known-source cases."""
    latent_probs_latent = [r["latent_prob"] for r in results if r["true_mmsi"] == "LATENT_SOURCE"]
    latent_probs_known = [r["latent_prob"] for r in results if r["true_mmsi"] != "LATENT_SOURCE"]

    if not latent_probs_latent and not latent_probs_known:
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    data = []
    labels = []
    if latent_probs_known:
        data.append(latent_probs_known)
        labels.append("Known Source")
    if latent_probs_latent:
        data.append(latent_probs_latent)
        labels.append("Latent Source")

    bp = ax.boxplot(data, labels=labels, patch_artist=True)
    colors_box = ["#3498db", "#e74c3c"]
    for patch, color in zip(bp["boxes"], colors_box):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax.set_ylabel("P(LATENT_SOURCE)")
    ax.set_title("Latent Probability: Known vs Latent Cases")
    fig.tight_layout()
    fig.savefig(os.path.join(results_dir, "figures", "latent_boxplot.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    plot_results()
