import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
    data = experiment_data["synthetic_fairness"]
    epochs = range(1, len(data["losses"]["train"]) + 1)

    # Loss curves
    try:
        plt.figure()
        plt.plot(epochs, data["losses"]["train"], label="Train Loss")
        plt.plot(epochs, data["losses"]["val"], label="Validation Loss")
        plt.title("Training and Validation Loss\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_fairness_loss_curves.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating loss plot: {e}")
        plt.close()

    # Accuracy curves
    try:
        plt.figure()
        plt.plot(epochs, data["metrics"]["train"], label="Train Accuracy")
        plt.plot(epochs, data["metrics"]["val"], label="Validation Accuracy")
        plt.title("Training and Validation Accuracy\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Accuracy")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_fairness_accuracy_curves.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating accuracy plot: {e}")
        plt.close()

    # Fairness metrics
    try:
        plt.figure()
        plt.plot(epochs, data["fairness"]["train"], label="Train Fairness")
        plt.plot(epochs, data["fairness"]["val"], label="Validation Fairness")
        plt.title("Demographic Parity Difference\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Fairness Metric")
        plt.legend()
        plt.savefig(
            os.path.join(working_dir, "synthetic_fairness_fairness_metrics.png")
        )
        plt.close()
    except Exception as e:
        print(f"Error creating fairness plot: {e}")
        plt.close()

    # Fairness gap
    try:
        plt.figure()
        plt.plot(epochs, data["fairness_gap"], label="Fairness Gap")
        plt.title("Train-Validation Fairness Gap\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Fairness Gap")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_fairness_fairness_gap.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating fairness gap plot: {e}")
        plt.close()

except Exception as e:
    print(f"Error loading experiment data: {e}")
