import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
except Exception as e:
    print(f"Error loading experiment data: {e}")

try:
    # Accuracy comparison plot
    metrics = experiment_data["synthetic_2d"]["metrics"]
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(2)
    width = 0.35
    ax.bar(
        x - width / 2,
        [metrics["clean"]["dense"], metrics["adversarial"]["dense"]],
        width,
        label="Dense",
    )
    ax.bar(
        x + width / 2,
        [metrics["clean"]["sparse"], metrics["adversarial"]["sparse"]],
        width,
        label="Sparse",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(["Clean Accuracy", "Adversarial Accuracy"])
    ax.set_ylabel("Accuracy")
    ax.set_title("Model Performance Comparison on Synthetic 2D Dataset")
    ax.legend()
    plt.savefig(os.path.join(working_dir, "accuracy_comparison.png"))
    plt.close()
except Exception as e:
    print(f"Error creating accuracy plot: {e}")
    plt.close()

try:
    # Sparsity comparison plot
    sparsity = experiment_data["synthetic_2d"]["sparsity"]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(["Dense", "Sparse"], [sparsity["dense"], sparsity["sparse"]])
    ax.set_ylabel("Number of Non-zero Parameters")
    ax.set_title("Model Sparsity Comparison on Synthetic 2D Dataset")
    plt.savefig(os.path.join(working_dir, "sparsity_comparison.png"))
    plt.close()
except Exception as e:
    print(f"Error creating sparsity plot: {e}")
    plt.close()
