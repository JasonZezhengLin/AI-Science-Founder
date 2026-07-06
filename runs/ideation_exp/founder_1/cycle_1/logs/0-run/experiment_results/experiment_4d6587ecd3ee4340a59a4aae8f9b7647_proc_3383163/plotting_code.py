import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
    data = experiment_data["synthetic_fairness"]

    # Plot training loss
    try:
        plt.figure()
        plt.plot(data["losses"])
        plt.title("Training Loss Curve\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Cross Entropy Loss")
        plt.savefig(os.path.join(working_dir, "synthetic_fairness_loss.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating loss plot: {e}")
        plt.close()

    # Plot DP gaps
    try:
        plt.figure()
        plt.plot(data["train_dp"], label="Train DP Gap")
        plt.plot(data["val_dp"], label="Validation DP Gap")
        plt.title("Demographic Parity Gap\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("DP Gap")
        plt.legend()
        plt.savefig(os.path.join(working_dir, "synthetic_fairness_dp_gaps.png"))
        plt.close()
    except Exception as e:
        print(f"Error creating DP gap plot: {e}")
        plt.close()

    # Plot generalization gap
    try:
        plt.figure()
        plt.plot(data["generalization_gap"])
        plt.title("Generalization Gap (Train vs Val DP)\nSynthetic Fairness Dataset")
        plt.xlabel("Epoch")
        plt.ylabel("Generalization Gap")
        plt.savefig(
            os.path.join(working_dir, "synthetic_fairness_generalization_gap.png")
        )
        plt.close()
    except Exception as e:
        print(f"Error creating generalization gap plot: {e}")
        plt.close()

except Exception as e:
    print(f"Error loading experiment data: {e}")
