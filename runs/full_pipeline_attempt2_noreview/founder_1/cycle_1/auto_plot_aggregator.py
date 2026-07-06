import os
import numpy as np
import matplotlib.pyplot as plt

# Ensure the figures directory exists
os.makedirs("figures", exist_ok=True)

# Load .npy files (replace with actual paths from the JSON summaries)
# Example paths (these should be replaced with actual paths from the JSON summaries):
# baseline_data = np.load("path/to/baseline.npy")
# research_data = np.load("path/to/research.npy")
# ablation_data = np.load("path/to/ablation.npy")

# Plot 1: Loss vs Epoch Comparison
try:
    fig, ax = plt.subplots(figsize=(8, 6))
    # Example data plotting (replace with actual data)
    # ax.plot(baseline_data, label="Baseline")
    # ax.plot(research_data, label="Proposed Method")
    # ax.plot(ablation_data, label="Ablation")
    ax.set_xlabel("Epoch", fontsize=14)
    ax.set_ylabel("Loss", fontsize=14)
    ax.set_title("Loss vs Epoch Across Methods", fontsize=16)
    ax.legend(fontsize=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.savefig("figures/loss_vs_epoch_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
except Exception as e:
    print(f"Error generating Plot 1: {e}")

# Plot 2: Average Loss Comparison
try:
    fig, ax = plt.subplots(figsize=(8, 6))
    # Example data plotting (replace with actual data)
    # categories = ['Baseline', 'Proposed Method', 'Ablation']
    # values = [np.mean(baseline_data), np.mean(research_data), np.mean(ablation_data)]
    # ax.bar(categories, values, color=['blue', 'orange', 'green'])
    ax.set_xlabel("Method", fontsize=14)
    ax.set_ylabel("Average Loss", fontsize=14)
    ax.set_title("Comparison of Average Loss Across Methods", fontsize=16)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.savefig("figures/average_loss_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
except Exception as e:
    print(f"Error generating Plot 2: {e}")

# Plot 3: Multi-Subplot Loss Comparison
try:
    fig, axs = plt.subplots(1, 3, figsize=(18, 6))
    # Example data plotting (replace with actual data)
    # axs[0].plot(baseline_data, label="Baseline")
    # axs[1].plot(research_data, label="Proposed Method")
    # axs[2].plot(ablation_data, label="Ablation")
    for i, ax in enumerate(axs):
        ax.set_xlabel("Epoch", fontsize=14)
        ax.set_ylabel("Loss", fontsize=14)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.legend(fontsize=12)
    plt.savefig("figures/multi_subplot_loss_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
except Exception as e:
    print(f"Error generating Plot 3: {e}")

# Plot 4: Example Plot with Key Numbers (Replace with actual data and labels)
try:
    fig, ax = plt.subplots(figsize=(8, 6))
    # Example data plotting (replace with actual data)
    # ax.plot(baseline_data, label="Baseline")
    # ax.plot(research_data, label="Proposed Method")
    # ax.plot(ablation_data, label="Ablation")
    ax.set_xlabel("Epoch", fontsize=14)
    ax.set_ylabel("Accuracy", fontsize=14)
    ax.set_title("Accuracy vs Epoch Across Methods", fontsize=16)
    ax.legend(fontsize=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.savefig("figures/accuracy_vs_epoch_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
except Exception as e:
    print(f"Error generating Plot 4: {e}")

# Add more plots as needed, ensuring they are unique and based on actual data.

# Final Note: Replace example data loading and plotting with actual data paths and plotting logic from the JSON summaries.