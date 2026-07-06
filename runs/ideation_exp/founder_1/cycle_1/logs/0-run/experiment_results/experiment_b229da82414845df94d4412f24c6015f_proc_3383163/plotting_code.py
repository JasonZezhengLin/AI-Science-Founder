import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
    data = experiment_data["synthetic_fairness"]
except Exception as e:
    print(f"Error loading experiment data: {e}")

try:
    # Accuracy plot
    plt.figure(figsize=(10, 5))
    plt.plot(data["metrics"]["train_acc"], label="Train Accuracy")
    plt.plot(data["metrics"]["val_acc"], label="Validation Accuracy")
    plt.title("Synthetic Fairness: Accuracy Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_fairness_accuracy.png"))
    plt.close()
except Exception as e:
    print(f"Error creating accuracy plot: {e}")
    plt.close()

try:
    # Fairness metrics plot
    plt.figure(figsize=(10, 5))
    plt.plot(data["metrics"]["train_fair"], label="Train Fairness Gap")
    plt.plot(data["metrics"]["val_fair"], label="Validation Fairness Gap")
    plt.title("Synthetic Fairness: Demographic Parity Gap Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Fairness Gap")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_fairness_fairness_gap.png"))
    plt.close()
except Exception as e:
    print(f"Error creating fairness plot: {e}")
    plt.close()

try:
    # Loss plot
    plt.figure(figsize=(10, 5))
    plt.plot(data["losses"]["train"], label="Train Loss")
    plt.plot(data["losses"]["val"], label="Validation Loss")
    plt.title("Synthetic Fairness: Loss Over Epochs")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_fairness_loss.png"))
    plt.close()
except Exception as e:
    print(f"Error creating loss plot: {e}")
    plt.close()
