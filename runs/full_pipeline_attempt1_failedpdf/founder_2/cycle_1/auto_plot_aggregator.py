import os
import numpy as np
import matplotlib.pyplot as plt

# Create figures directory
os.makedirs("figures", exist_ok=True)

# Set global plot settings
plt.rcParams.update({'font.size': 12, 'axes.labelsize': 14, 'xtick.labelsize': 12, 'ytick.labelsize': 12})
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False

# Plot 1: Training Loss Comparison
try:
    # Load data (replace with actual paths from JSON summaries)
    baseline_loss = np.load("/path/to/baseline_loss.npy")
    research_loss = np.load("/path/to/research_loss.npy")
    
    # Create plot
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(baseline_loss, label="Baseline Loss")
    ax.plot(research_loss, label="Research Loss")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title("Training Loss Comparison")
    ax.legend()
    plt.tight_layout()
    plt.savefig("figures/training_loss_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()
except Exception as e:
    print(f"Error generating Plot 1: {e}")

# Plot 2: Accuracy vs. Epoch
try:
    # Load data (replace with actual paths from JSON summaries)
    baseline_acc = np.load("/path/to/baseline_acc.npy")
    research_acc = np.load("/path/to/research_acc.npy")
    
    # Create plot
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(baseline_acc, label="Baseline Accuracy")
    ax.plot(research_acc, label="Research Accuracy")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs. Epoch")
    ax.legend()
    plt.tight_layout()
    plt.savefig("figures/accuracy_vs_epoch.png", dpi=300, bbox_inches="tight")
    plt.close()
except Exception as e:
    print(f"Error generating Plot 2: {e}")

# Plot 3: Ablation Study Results
try:
    # Load data (replace with actual paths from JSON summaries)
    ablation_results = np.load("/path/to/ablation_results.npy")
    
    # Create plot
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(range(len(ablation_results)), ablation_results, label="Ablation Results")
    ax.set_xlabel("Ablation Variant")
    ax.set_ylabel("Performance Metric")
    ax.set_title("Ablation Study Results")
    ax.legend()
    plt.tight_layout()
    plt.savefig("figures/ablation_study_results.png", dpi=300, bbox_inches="tight")
    plt.close()
except Exception as e:
    print(f"Error generating Plot 3: {e}")

# Add more plots as needed, ensuring each plot is unique and meaningful for the final paper.
# Replace paths and logic with actual data and plotting code from the JSON summaries.