import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import accuracy_score

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Generate synthetic data with sensitive attribute
np.random.seed(0)
n_samples = 1000
X = np.random.randn(n_samples, 2)
sensitive = np.random.randint(0, 2, size=n_samples)  # Binary sensitive attribute
y = ((X[:, 0] > 0) & (X[:, 1] > 0)).astype(int)  # Simple decision boundary

# Split into train/val
train_idx = np.random.choice(n_samples, int(0.8 * n_samples), replace=False)
val_idx = np.array([i for i in range(n_samples) if i not in train_idx])
X_train, X_val = X[train_idx], X[val_idx]
y_train, y_val = y[train_idx], y[val_idx]
s_train, s_val = sensitive[train_idx], sensitive[val_idx]

# Convert to tensors and move to device
X_train = torch.FloatTensor(X_train).to(device)
y_train = torch.LongTensor(y_train).to(device)
s_train = torch.LongTensor(s_train).to(device)
X_val = torch.FloatTensor(X_val).to(device)
y_val = torch.LongTensor(y_val).to(device)
s_val = torch.LongTensor(s_val).to(device)

# Define model
model = nn.Sequential(nn.Linear(2, 16), nn.ReLU(), nn.Linear(16, 2)).to(device)


# Define fairness metric (demographic parity difference)
def demographic_parity(logits, sensitive):
    preds = logits.argmax(dim=1)
    group0 = sensitive == 0
    group1 = sensitive == 1
    prob0 = preds[group0].float().mean()
    prob1 = preds[group1].float().mean()
    return torch.abs(prob0 - prob1)


# Training setup
optimizer = optim.Adam(model.parameters(), lr=0.01)
criterion = nn.CrossEntropyLoss()

# Track metrics
experiment_data = {
    "synthetic_fairness": {
        "losses": {"train": [], "val": []},
        "metrics": {"train": [], "val": []},
        "fairness": {"train": [], "val": []},
        "fairness_gap": [],
    }
}

# Training loop
n_epochs = 20
batch_size = 32
for epoch in range(n_epochs):
    model.train()
    train_loss = 0
    for i in range(0, len(X_train), batch_size):
        xb = X_train[i : i + batch_size]
        yb = y_train[i : i + batch_size]
        sb = s_train[i : i + batch_size]

        optimizer.zero_grad()
        logits = model(xb)
        loss = criterion(logits, yb)
        loss.backward()
        optimizer.step()
        train_loss += loss.item()

    # Eval on train and val
    model.eval()
    with torch.no_grad():
        # Train metrics
        train_logits = model(X_train)
        train_loss = criterion(train_logits, y_train).item()
        train_acc = (train_logits.argmax(dim=1) == y_train).float().mean().item()
        train_fairness = demographic_parity(train_logits, s_train).item()

        # Val metrics
        val_logits = model(X_val)
        val_loss = criterion(val_logits, y_val).item()
        val_acc = (val_logits.argmax(dim=1) == y_val).float().mean().item()
        val_fairness = demographic_parity(val_logits, s_val).item()

        # Fairness gap
        fairness_gap = abs(train_fairness - val_fairness)

        # Store metrics
        experiment_data["synthetic_fairness"]["losses"]["train"].append(train_loss)
        experiment_data["synthetic_fairness"]["losses"]["val"].append(val_loss)
        experiment_data["synthetic_fairness"]["metrics"]["train"].append(train_acc)
        experiment_data["synthetic_fairness"]["metrics"]["val"].append(val_acc)
        experiment_data["synthetic_fairness"]["fairness"]["train"].append(
            train_fairness
        )
        experiment_data["synthetic_fairness"]["fairness"]["val"].append(val_fairness)
        experiment_data["synthetic_fairness"]["fairness_gap"].append(fairness_gap)

        print(f"Epoch {epoch}: Train Loss={train_loss:.4f}, Val Loss={val_loss:.4f}")
        print(
            f"Train Fairness={train_fairness:.4f}, Val Fairness={val_fairness:.4f}, Gap={fairness_gap:.4f}"
        )

# Save results
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Print final metrics
final_metrics = {
    "final_train_fairness": experiment_data["synthetic_fairness"]["fairness"]["train"][
        -1
    ],
    "final_val_fairness": experiment_data["synthetic_fairness"]["fairness"]["val"][-1],
    "final_fairness_gap": experiment_data["synthetic_fairness"]["fairness_gap"][-1],
    "final_val_accuracy": experiment_data["synthetic_fairness"]["metrics"]["val"][-1],
}
print("\nFinal Metrics:")
for k, v in final_metrics.items():
    print(f"{k}: {v:.4f}")
