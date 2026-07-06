import matplotlib.pyplot as plt
import numpy as np
import os

working_dir = os.path.join(os.getcwd(), "working")

try:
    experiment_data = np.load(
        os.path.join(working_dir, "experiment_data.npy"), allow_pickle=True
    ).item()
except Exception as e:
    print(f"Error loading experiment data: {e}")

try:
    plt.figure()
    plt.bar(
        ["Dense", "Sparse"],
        [
            experiment_data["synthetic_data"]["metrics"]["dense_clean_acc"],
            experiment_data["synthetic_data"]["metrics"]["sparse_clean_acc"],
        ],
    )
    plt.title("Synthetic Data: Clean Accuracy Comparison")
    plt.ylabel("Accuracy")
    plt.savefig(os.path.join(working_dir, "synthetic_clean_accuracy.png"))
    plt.close()
except Exception as e:
    print(f"Error creating clean accuracy plot: {e}")
    plt.close()

try:
    plt.figure()
    plt.bar(
        ["Dense", "Sparse"],
        [
            experiment_data["synthetic_data"]["metrics"]["dense_adv_acc"],
            experiment_data["synthetic_data"]["metrics"]["sparse_adv_acc"],
        ],
    )
    plt.title("Synthetic Data: Adversarial Accuracy Comparison")
    plt.ylabel("Accuracy")
    plt.savefig(os.path.join(working_dir, "synthetic_adversarial_accuracy.png"))
    plt.close()
except Exception as e:
    print(f"Error creating adversarial accuracy plot: {e}")
    plt.close()

try:
    plt.figure()
    plt.bar(
        ["Feature 1", "Feature 2"],
        experiment_data["synthetic_data"]["feature_importance"]["dense"],
        alpha=0.5,
        label="Dense",
    )
    plt.bar(
        ["Feature 1", "Feature 2"],
        experiment_data["synthetic_data"]["feature_importance"]["sparse"],
        alpha=0.5,
        label="Sparse",
    )
    plt.title("Synthetic Data: Feature Importance Comparison")
    plt.ylabel("Importance Score")
    plt.legend()
    plt.savefig(os.path.join(working_dir, "synthetic_feature_importance.png"))
    plt.close()
except Exception as e:
    print(f"Error creating feature importance plot: {e}")
    plt.close()
