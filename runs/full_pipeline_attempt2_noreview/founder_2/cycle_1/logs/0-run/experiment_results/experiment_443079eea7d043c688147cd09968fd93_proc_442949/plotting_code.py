import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()

    # Extract metrics
    dense_metrics = experiment_data["synthetic_binary"]["metrics"]["dense"]
    sparse_metrics = experiment_data["synthetic_binary"]["metrics"]["sparse"]

    # Plot 1: Clean vs Adversarial Accuracy
    plt.figure()
    labels = ["Dense Model", "Sparse Model"]
    clean_acc = [dense_metrics["clean_acc"], sparse_metrics["clean_acc"]]
    adv_acc = [dense_metrics["adv_acc"], sparse_metrics["adv_acc"]]

    x = np.arange(len(labels))
    width = 0.35

    plt.bar(x - width / 2, clean_acc, width, label="Clean Accuracy")
    plt.bar(x + width / 2, adv_acc, width, label="Adversarial Accuracy")
    plt.xticks(x, labels)
    plt.ylabel("Accuracy")
    plt.title("Clean vs Adversarial Accuracy")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "accuracy_comparison.png"))
    plt.close()

    # Plot 2: Robustness Drop
    plt.figure()
    robustness_drop = [
        dense_metrics["robustness_drop"],
        sparse_metrics["robustness_drop"],
    ]
    plt.plot(labels, robustness_drop, marker="o")
    plt.ylabel("Robustness Drop")
    plt.title("Robustness Drop Comparison")
    plt.savefig(os.path.join(working_dir, "robustness_drop.png"))
    plt.close()

except Exception as e:
    print(f"Error creating plots: {e}")
    plt.close()
