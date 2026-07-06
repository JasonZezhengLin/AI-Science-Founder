import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Generate synthetic data with sensitive attribute
n_train, n_val = 1000, 200
np.random.seed(0)
X_train = np.random.randn(n_train, 10).astype(np.float32)
s_train = np.random.randint(0, 2, size=n_train)  # sensitive attribute
y_train = ((X_train[:, 0] > 0) ^ (s_train == 1)).astype(np.float32)  # XOR relationship

X_val = np.random.randn(n_val, 10).astype(np.float32)
s_val = np.random.randint(0, 2, size=n_val)
y_val = ((X_val[:, 0] > 0) ^ (s_val == 1)).astype(np.float32)

X_train, s_train, y_train = (
    torch.tensor(X_train).to(device),
    torch.tensor(s_train).to(device),
    torch.tensor(y_train).to(device),
)
X_val, s_val, y_val = (
    torch.tensor(X_val).to(device),
    torch.tensor(s_val).to(device),
    torch.tensor(y_val).to(device),
)

# Define model and fairness metrics
model = nn.Sequential(nn.Linear(10, 20), nn.ReLU(), nn.Linear(20, 1), nn.Sigmoid()).to(
    device
)
optimizer = optim.Adam(model.parameters(), lr=0.01)
criterion = nn.BCELoss()


def demographic_parity(output, sensitive):
    protected = sensitive == 1
    return torch.abs(output[protected].mean() - output[~protected].mean())


experiment_data = {
    "synthetic_data": {
        "losses": {"train": [], "val": []},
        "metrics": {"train": [], "val": []},
        "fairness_gap": [],
    }
}

# Training loop
for epoch in range(30):
    model.train()
    train_output = model(X_train).squeeze()
    train_loss = criterion(train_output, y_train)
    train_dp = demographic_parity(train_output, s_train)

    optimizer.zero_grad()
    train_loss.backward()
    optimizer.step()

    model.eval()
    with torch.no_grad():
        val_output = model(X_val).squeeze()
        val_loss = criterion(val_output, y_val)
        val_dp = demographic_parity(val_output, s_val)

    experiment_data["synthetic_data"]["losses"]["train"].append(train_loss.item())
    experiment_data["synthetic_data"]["losses"]["val"].append(val_loss.item())
    experiment_data["synthetic_data"]["metrics"]["train"].append(train_dp.item())
    experiment_data["synthetic_data"]["metrics"]["val"].append(val_dp.item())
    fairness_gap = abs(train_dp.item() - val_dp.item())
    experiment_data["synthetic_data"]["fairness_gap"].append(fairness_gap)

    print(
        f"Epoch {epoch}: train_loss={train_loss:.4f}, val_loss={val_loss:.4f}, "
        f"train_dp={train_dp:.4f}, val_dp={val_dp:.4f}, fairness_gap={fairness_gap:.4f}"
    )

np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)
