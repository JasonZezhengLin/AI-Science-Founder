import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
    data = experiment_data["synthetic_2d"]

    try:
        plt.figure()
        plt.plot(data["losses"]["train"], label="Train Loss")
        plt.plot(data["losses"]["val"], label="Val Loss")
        plt.title("Training and Validation Loss Over Epochs\nDataset: Synthetic 2D")
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_2d_loss_curves.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating loss plot: {e}")
        plt.close()

    try:
        plt.figure()
        plt.plot(data["metrics"]["train"], label="Train Accuracy")
        plt.plot(data["metrics"]["val"], label="Val Accuracy")
        plt.title("Training and Validation Accuracy Over Epochs\nDataset: Synthetic 2D")
        plt.xlabel("Epoch")
        plt.ylabel("Accuracy")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_2d_accuracy_curves.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating accuracy plot: {e}")
        plt.close()

    try:
        plt.figure()
        plt.plot(data["dbcis"])
        plt.title(
            "Decision Boundary Complexity Index Over Epochs\nDataset: Synthetic 2D"
        )
        plt.xlabel("Epoch")
        plt.ylabel("DBCI")
        plt.savefig(os.path.join(working_dir, "synthetic_2d_dbci_curve.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating dbci plot: {e}")
        plt.close()

except Exception as e:
    print(f"Error loading experiment data: {e}")
