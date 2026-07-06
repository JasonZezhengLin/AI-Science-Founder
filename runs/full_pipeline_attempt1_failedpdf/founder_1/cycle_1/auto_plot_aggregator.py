import os
import numpy as np
import matplotlib.pyplot as plt

# Ensure the figures directory exists
os.makedirs("figures", exist_ok=True)

# Set global plotting parameters for better readability
plt.rcParams.update({'font.size': 12, 'axes.labelsize': 14, 'xtick.labelsize': 12, 'ytick.labelsize': 12})

# Example plot 1: Performance comparison across different models
try:
    # Load data (example paths based on assumed JSON structure)
    baseline_performance = np.load("exp_results_npy_files/baseline_performance.npy")
    research_performance = np.load("exp_results_npy_files/research_performance.npy")
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(baseline_performance, label="Baseline Model", marker="o")
    ax.plot(research_performance, label="Proposed Model", marker="s")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Accuracy")
    ax.set_title("Comparison of Accuracy Between Baseline and Proposed Models Over Epochs")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig("figures/model_performance_comparison.png", dpi=300)
    plt.close()
except Exception as e:
    print(f"Error generating model performance comparison plot: {e}")

# Example plot 2: Ablation study results
try:
    # Load data (example paths based on assumed JSON structure)
    ablation_results = np.load("exp_results_npy_files/ablation_results.npy")
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(range(len(ablation_results)), ablation_results, tick_label=["Feature A", "Feature B", "Feature C"])
    ax.set_xlabel("Ablated Feature")
    ax.set_ylabel("Performance Drop (%)")
    ax.set_title("Impact of Ablating Different Features on Model Performance")
    plt.tight_layout()
    plt.savefig("figures/ablation_study_results.png", dpi=300)
    plt.close()
except Exception as e:
    print(f"Error generating ablation study plot: {e}")

# Example plot 3: Training loss comparison
try:
    # Load data (example paths based on assumed JSON structure)
    baseline_loss = np.load("exp_results_npy_files/baseline_loss.npy")
    research_loss = np.load("exp_results_npy_files/research_loss.npy")
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(baseline_loss, label="Baseline Model", linestyle="--")
    ax.plot(research_loss, label="Proposed Model", linestyle="-")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Training Loss")
    ax.set_title("Training Loss Comparison Between Baseline and Proposed Models")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig("figures/training_loss_comparison.png", dpi=300)
    plt.close()
except Exception as e:
    print(f"Error generating training loss comparison plot: {e}")

# Example plot 4: Confusion matrix for the proposed model
try:
    # Load data (example paths based on assumed JSON structure)
    confusion_matrix = np.load("exp_results_npy_files/research_confusion_matrix.npy")
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(8, 6))
    cax = ax.matshow(confusion_matrix, cmap="Blues")
    fig.colorbar(cax)
    ax.set_xlabel("Predicted Label")
    ax.set_ylabel("True Label")
    ax.set_title("Confusion Matrix for the Proposed Model")
    plt.tight_layout()
    plt.savefig("figures/confusion_matrix_proposed_model.png", dpi=300)
    plt.close()
except Exception as e:
    print(f"Error generating confusion matrix plot: {e}")

# Add more plots as needed based on the actual data and findings from the JSON summaries.