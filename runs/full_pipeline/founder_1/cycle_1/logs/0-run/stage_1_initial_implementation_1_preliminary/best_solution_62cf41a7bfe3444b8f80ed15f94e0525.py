import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from torch.autograd import grad

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Synthetic dataset
n_samples = 1000
X = torch.randn(n_samples, 10).to(device)
y = (X[:, 0] + 0.5 * X[:, 1] - 0.3 * X[:, 2] > 0).float().to(device)
X_train, X_test = X[:800], X[800:]
y_train, y_test = y[:800], y[800:]

# Model
model = nn.Sequential(nn.Linear(10, 32), nn.ReLU(), nn.Linear(32, 1), nn.Sigmoid()).to(
    device
)
optimizer = optim.Adam(model.parameters(), lr=0.01)
criterion = nn.BCELoss()


# IGAT training
def get_feature_importance(model, x, y):
    x.requires_grad_(True)
    output = model(x)
    loss = criterion(output, y.unsqueeze(1))
    grads = grad(loss, x)[0]
    return torch.abs(grads)


def igat_attack(x, y, model, eps=0.1):
    importance = get_feature_importance(model, x, y)
    perturbation = eps * torch.sign(importance)
    return torch.clamp(x + perturbation, -1, 1)


experiment_data = {
    "synthetic": {
        "metrics": {"train": [], "val": [], "train_robust": [], "val_robust": []},
        "losses": {"train": [], "val": []},
    }
}

n_epochs = 20
for epoch in range(n_epochs):
    model.train()
    # Standard training
    optimizer.zero_grad()
    outputs = model(X_train)
    loss = criterion(outputs, y_train.unsqueeze(1))
    loss.backward()
    optimizer.step()

    # IGAT training
    x_adv = igat_attack(X_train, y_train, model)
    optimizer.zero_grad()
    outputs_adv = model(x_adv)
    loss_adv = criterion(outputs_adv, y_train.unsqueeze(1))
    loss_adv.backward()
    optimizer.step()

    # Evaluation
    model.eval()
    with torch.no_grad():
        train_pred = model(X_train).round()
        train_acc = (train_pred.squeeze() == y_train).float().mean()
        test_pred = model(X_test).round()
        test_acc = (test_pred.squeeze() == y_test).float().mean()

        # Robustness evaluation
        x_test_adv = igat_attack(X_test, y_test, model)
        test_robust_pred = model(x_test_adv).round()
        test_robust_acc = (test_robust_pred.squeeze() == y_test).float().mean()

    experiment_data["synthetic"]["metrics"]["train"].append(train_acc.item())
    experiment_data["synthetic"]["metrics"]["val"].append(test_acc.item())
    experiment_data["synthetic"]["metrics"]["val_robust"].append(test_robust_acc.item())
    experiment_data["synthetic"]["losses"]["train"].append(loss.item())

    print(
        f"Epoch {epoch}: Train Acc={train_acc:.4f}, Test Acc={test_acc:.4f}, Robust Acc={test_robust_acc:.4f}"
    )

# Calculate RIR (Robustness Improvement Ratio)
baseline_robust = np.mean(
    [x for x in experiment_data["synthetic"]["metrics"]["val_robust"][:5]]
)
final_robust = np.mean(
    [x for x in experiment_data["synthetic"]["metrics"]["val_robust"][-5:]]
)
rir = (final_robust - baseline_robust) / baseline_robust
print(f"Robustness Improvement Ratio (RIR): {rir:.4f}")

# Save results
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Plot training curves
plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.plot(experiment_data["synthetic"]["metrics"]["train"], label="Train Acc")
plt.plot(experiment_data["synthetic"]["metrics"]["val"], label="Test Acc")
plt.plot(experiment_data["synthetic"]["metrics"]["val_robust"], label="Robust Acc")
plt.legend()
plt.title("Accuracy Curves")

plt.subplot(1, 2, 2)
plt.plot(experiment_data["synthetic"]["losses"]["train"], label="Train Loss")
plt.legend()
plt.title("Training Loss")
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "training_curves.png"))
plt.close()
