import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
    synthetic_data = experiment_data["synthetic_data"]
except Exception as e:
    print(f"Error loading experiment data: {e}")

try:
    plt.figure()
    plt.plot(synthetic_data["losses"]["train"], label="Train Loss")
    plt.plot(synthetic_data["losses"]["val"], label="Validation Loss")
    plt.title("Training and Validation Loss Curves")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_data_loss_curves.png"))
    plt.close()
except Exception as e:
    print(f"Error creating loss plot: {e}")
    plt.close()

try:
    plt.figure()
    plt.plot(synthetic_data["metrics"]["train"], label="Train DP")
    plt.plot(synthetic_data["metrics"]["val"], label="Validation DP")
    plt.title("Demographic Parity Metric Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Demographic Parity")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_data_dp_metrics.png"))
    plt.close()
except Exception as e:
    print(f"Error creating DP plot: {e}")
    plt.close()

try:
    plt.figure()
    plt.plot(synthetic_data["fairness_gap"])
    plt.title("Fairness Gap Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Fairness Gap")
    plt.savefig(os.path.join(working_dir, "synthetic_data_fairness_gap.png"))
    plt.close()
except Exception as e:
    print(f"Error creating fairness gap plot: {e}")
    plt.close()
