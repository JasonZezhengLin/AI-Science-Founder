import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import accuracy_score

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Generate synthetic data with sensitive attribute
np.random.seed(0)
n_samples = 1000
X = np.random.randn(n_samples, 2) * 1.5
sensitive = np.random.binomial(1, 0.5, n_samples)  # Binary sensitive attribute
y = ((X[:, 0] + X[:, 1] + 0.5 * sensitive) > 0).astype(
    int
)  # Label depends slightly on sensitive attribute

# Split into train/val (80/20)
split = int(0.8 * n_samples)
X_train, X_val = X[:split], X[split:]
y_train, y_val = y[:split], y[split:]
s_train, s_val = sensitive[:split], sensitive[split:]

# Convert to tensors and move to device
X_train = torch.FloatTensor(X_train).to(device)
y_train = torch.LongTensor(y_train).to(device)
s_train = torch.FloatTensor(s_train).to(device)
X_val = torch.FloatTensor(X_val).to(device)
y_val = torch.LongTensor(y_val).to(device)
s_val = torch.FloatTensor(s_val).to(device)

# Define model
model = nn.Sequential(nn.Linear(2, 16), nn.ReLU(), nn.Linear(16, 2)).to(device)


# Define fairness metric (demographic parity difference)
def demographic_parity(logits, sensitive):
    preds = logits.argmax(dim=1).float()
    dp_diff = torch.abs(preds[sensitive == 1].mean() - preds[sensitive == 0].mean())
    return dp_diff


# Training setup
optimizer = optim.Adam(model.parameters(), lr=0.01)
criterion = nn.CrossEntropyLoss()
fairness_lambda = 0.1  # Fairness regularization strength

# Training loop
n_epochs = 20
experiment_data = {
    "synthetic_fairness": {
        "metrics": {"train_acc": [], "val_acc": [], "train_fair": [], "val_fair": []},
        "losses": {"train": [], "val": []},
        "fairness_gap": [],
    }
}

for epoch in range(n_epochs):
    model.train()
    optimizer.zero_grad()
    logits = model(X_train)
    loss = criterion(logits, y_train)
    fair_loss = demographic_parity(logits, s_train)
    total_loss = loss + fairness_lambda * fair_loss
    total_loss.backward()
    optimizer.step()

    # Evaluate on training set
    with torch.no_grad():
        train_logits = model(X_train)
        train_acc = accuracy_score(y_train.cpu(), train_logits.argmax(dim=1).cpu())
        train_fair = demographic_parity(train_logits, s_train).item()

        # Evaluate on validation set
        val_logits = model(X_val)
        val_loss = criterion(val_logits, y_val).item()
        val_acc = accuracy_score(y_val.cpu(), val_logits.argmax(dim=1).cpu())
        val_fair = demographic_parity(val_logits, s_val).item()

        fairness_gap = abs(train_fair - val_fair)

        experiment_data["synthetic_fairness"]["metrics"]["train_acc"].append(train_acc)
        experiment_data["synthetic_fairness"]["metrics"]["val_acc"].append(val_acc)
        experiment_data["synthetic_fairness"]["metrics"]["train_fair"].append(
            train_fair
        )
        experiment_data["synthetic_fairness"]["metrics"]["val_fair"].append(val_fair)
        experiment_data["synthetic_fairness"]["losses"]["train"].append(loss.item())
        experiment_data["synthetic_fairness"]["losses"]["val"].append(val_loss)
        experiment_data["synthetic_fairness"]["fairness_gap"].append(fairness_gap)

        print(
            f"Epoch {epoch}: val_loss={val_loss:.4f}, train_fair={train_fair:.4f}, val_fair={val_fair:.4f}, fairness_gap={fairness_gap:.4f}"
        )

np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)
