import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
import os

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Synthetic data with sensitive attribute (s) and labels (y)
n_train, n_val = 1000, 300
torch.manual_seed(0)

# Group 0 (s=0)
X0 = torch.cat(
    [
        torch.randn(n_train // 4, 2) * 0.5 + torch.tensor([-1, -1]),
        torch.randn(n_train // 4, 2) * 0.5 + torch.tensor([2, 2]),
    ]
)
y0 = torch.cat([torch.zeros(n_train // 4), torch.ones(n_train // 4)]).long()
s0 = torch.zeros(n_train // 2)

# Group 1 (s=1)
X1 = torch.randn(n_train // 2, 2) * 0.7 + torch.tensor([0, 0])
y1 = (torch.rand(n_train // 2) > 0.7).long()
s1 = torch.ones(n_train // 2)

X_train = torch.cat([X0, X1]).to(device)
y_train = torch.cat([y0, y1]).to(device)
s_train = torch.cat([s0, s1]).to(device)

# Validation data
X0_val = torch.cat(
    [
        torch.randn(n_val // 4, 2) * 0.5 + torch.tensor([-1, -1]),
        torch.randn(n_val // 4, 2) * 0.5 + torch.tensor([2, 2]),
    ]
)
y0_val = torch.cat([torch.zeros(n_val // 4), torch.ones(n_val // 4)]).long()
s0_val = torch.zeros(n_val // 2)

X1_val = torch.randn(n_val // 2, 2) * 0.7 + torch.tensor([0, 0])
y1_val = (torch.rand(n_val // 2) > 0.7).long()
s1_val = torch.ones(n_val // 2)

X_val = torch.cat([X0_val, X1_val]).to(device)
y_val = torch.cat([y0_val, y1_val]).to(device)
s_val = torch.cat([s0_val, s1_val]).to(device)

# Model
model = nn.Sequential(nn.Linear(2, 16), nn.ReLU(), nn.Linear(16, 2)).to(device)
optimizer = optim.Adam(model.parameters(), lr=0.01)
criterion = nn.CrossEntropyLoss()


def compute_dp_diff(y_pred, s):
    group0 = s == 0
    group1 = s == 1
    p0 = y_pred[group0].mean()
    p1 = y_pred[group1].mean()
    return abs(p0 - p1).item()


train_dps, val_dps, losses = [], [], []
for epoch in range(50):
    model.train()
    logits = model(X_train)
    loss = criterion(logits, y_train)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

    with torch.no_grad():
        y_pred_train = (logits.argmax(1)).float()
        train_dp = compute_dp_diff(y_pred_train, s_train)
        train_dps.append(train_dp)

        logits_val = model(X_val)
        y_pred_val = (logits_val.argmax(1)).float()
        val_dp = compute_dp_diff(y_pred_val, s_val)
        val_dps.append(val_dp)

        losses.append(loss.item())

    print(
        f"Epoch {epoch}: loss={loss.item():.4f}, Train DP gap={train_dp:.4f}, Val DP gap={val_dp:.4f}"
    )

generalization_gap = np.abs(np.array(train_dps) - np.array(val_dps))
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.plot(train_dps, label="Train DP gap")
plt.plot(val_dps, label="Val DP gap")
plt.legend()
plt.subplot(1, 2, 2)
plt.plot(generalization_gap, label="Generalization gap")
plt.legend()
plt.savefig(os.path.join(working_dir, "fairness_generalization.png"))

experiment_data = {
    "synthetic_fairness": {
        "losses": losses,
        "train_dp": train_dps,
        "val_dp": val_dps,
        "generalization_gap": generalization_gap.tolist(),
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)
