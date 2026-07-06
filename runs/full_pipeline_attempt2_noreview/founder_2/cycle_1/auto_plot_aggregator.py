import os
import numpy as np
import matplotlib.pyplot as plt

# Ensure the figures directory exists
os.makedirs("figures", exist_ok=True)

# Function to plot ablation study results
def plot_ablation_results():
    try:
        # Load ablation data (replace with actual paths from JSON summaries)
        ablation_data_path = "path/to/ablation_data.npy"  # Replace with actual path
        ablation_data = np.load(ablation_data_path)

        # Plot ablation results
        plt.figure(figsize=(8, 6))
        plt.bar(range(len(ablation_data)), ablation_data, label="Ablation Results")
        plt.xlabel("Ablation Variant", fontsize=14)
        plt.ylabel("Performance Metric", fontsize=14)
        plt.title("Ablation Study Results", fontsize=16)
        plt.legend(fontsize=12)
        plt.savefig("figures/ablation_results.png", dpi=300, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"Error in plot_ablation_results: {e}")

# Function to plot comparison with baseline
def plot_baseline_comparison():
    try:
        # Load baseline and research data (replace with actual paths from JSON summaries)
        baseline_data_path = "path/to/baseline_data.npy"  # Replace with actual path
        research_data_path = "path/to/research_data.npy"  # Replace with actual path
        baseline_data = np.load(baseline_data_path)
        research_data = np.load(research_data_path)

        # Plot comparison with baseline
        plt.figure(figsize=(8, 6))
        plt.plot(baseline_data[:, 0], baseline_data[:, 1], label="Baseline")
        plt.plot(research_data[:, 0], research_data[:, 1], label="Proposed Method")
        plt.xlabel("X Axis Label", fontsize=14)
        plt.ylabel("Y Axis Label", fontsize=14)
        plt.title("Comparison with Baseline", fontsize=16)
        plt.legend(fontsize=12)
        plt.savefig("figures/baseline_comparison.png", dpi=300, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"Error in plot_baseline_comparison: {e}")

# Function to plot empirical results
def plot_empirical_results():
    try:
        # Load empirical data (replace with actual paths from JSON summaries)
        empirical_data_path = "path/to/empirical_data.npy"  # Replace with actual path
        empirical_data = np.load(empirical_data_path)

        # Plot empirical results
        plt.figure(figsize=(8, 6))
        plt.plot(empirical_data[:, 0], empirical_data[:, 1], label="Empirical Data")
        plt.xlabel("X Axis Label", fontsize=14)
        plt.ylabel("Y Axis Label", fontsize=14)
        plt.title("Empirical Results", fontsize=16)
        plt.legend(fontsize=12)
        plt.savefig("figures/empirical_results.png", dpi=300, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"Error in plot_empirical_results: {e}")

# Function to plot synthetic data results
def plot_synthetic_data_results():
    try:
        # Load synthetic data (replace with actual paths from JSON summaries)
        synthetic_data_path = "path/to/synthetic_data.npy"  # Replace with actual path
        synthetic_data = np.load(synthetic_data_path)

        # Plot synthetic data results
        plt.figure(figsize=(8, 6))
        plt.plot(synthetic_data[:, 0], synthetic_data[:, 1], label="Synthetic Data")
        plt.xlabel("X Axis Label", fontsize=14)
        plt.ylabel("Y Axis Label", fontsize=14)
        plt.title("Synthetic Data Results", fontsize=16)
        plt.legend(fontsize=12)
        plt.savefig("figures/synthetic_data_results.png", dpi=300, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"Error in plot_synthetic_data_results: {e}")

# Main function to generate all plots
def generate_all_plots():
    plot_ablation_results()
    plot_baseline_comparison()
    plot_empirical_results()
    plot_synthetic_data_results()

# Run the plotting functions
if __name__ == "__main__":
    generate_all_plots()