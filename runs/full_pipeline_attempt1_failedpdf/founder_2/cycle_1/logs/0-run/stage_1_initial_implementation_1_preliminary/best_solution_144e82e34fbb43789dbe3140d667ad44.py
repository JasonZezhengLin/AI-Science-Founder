import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")


# Generate synthetic data with causal (x1) and spurious (x2) features
def generate_data(n_samples, shift=0.0):
    x1 = np.random.randn(n_samples)  # Causal feature
    x2 = x1 * 0.5 + shift * np.random.randn(
        n_samples
    )  # Spurious feature (shift affects correlation)
    y = (x1 > 0).astype(float)
    X = np.column_stack([x1, x2])
    return X.astype(np.float32), y.astype(np.int64)


# Train data (strong correlation between x1 and x2)
X_train, y_train = generate_data(1000, shift=0.1)
# Test data (weakened correlation to simulate distribution shift)
X_test, y_test = generate_data(500, shift=2.0)

# Convert to PyTorch tensors
X_train, y_train = torch.tensor(X_train).to(device), torch.tensor(y_train).to(device)
X_test, y_test = torch.tensor(X_test).to(device), torch.tensor(y_test).to(device)


# Standard MLP baseline
class BaselineModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, 16), nn.ReLU(), nn.Linear(16, 2))

    def forward(self, x):
        return self.net(x)


# Causal model that explicitly uses invariant features
class CausalModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.invariant_net = nn.Sequential(nn.Linear(1, 8), nn.ReLU(), nn.Linear(8, 2))
        self.full_net = nn.Sequential(nn.Linear(2, 16), nn.ReLU(), nn.Linear(16, 2))

    def forward(self, x, use_invariant=True):
        if use_invariant:
            return self.invariant_net(x[:, [0]])  # Only use x1 (causal feature)
        return self.full_net(x)


def train_model(model, X_train, y_train, X_test, y_test, epochs=50):
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()
    train_losses, test_losses = [], []
    metrics = []

    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        loss.backward()
        optimizer.step()
        train_losses.append(loss.item())

        # Evaluate
        model.eval()
        with torch.no_grad():
            test_outputs = model(X_test)
            test_loss = criterion(test_outputs, y_test).item()
            test_losses.append(test_loss)

            # Calculate Invariant Feature Utilization Score
            causal_preds = model(X_test, use_invariant=True).argmax(dim=1).cpu().numpy()
            full_preds = model(X_test, use_invariant=False).argmax(dim=1).cpu().numpy()
            causal_feature = X_test[:, 0].cpu().numpy()
            score = np.corrcoef(causal_preds, causal_feature)[0, 1]
            metrics.append(score)

        print(f"Epoch {epoch}: test_loss={test_loss:.4f}, IFUS={score:.4f}")

    return train_losses, test_losses, metrics


# Train both models
baseline = BaselineModel().to(device)
causal = CausalModel().to(device)

print("Training baseline model...")
bl_train_loss, bl_test_loss, bl_metrics = train_model(
    baseline, X_train, y_train, X_test, y_test
)

print("\nTraining causal model...")
ca_train_loss, ca_test_loss, ca_metrics = train_model(
    causal, X_train, y_train, X_test, y_test
)

# Save results
experiment_data = {
    "synthetic_causal": {
        "metrics": {"baseline": bl_metrics, "causal": ca_metrics},
        "losses": {
            "baseline_train": bl_train_loss,
            "baseline_test": bl_test_loss,
            "causal_train": ca_train_loss,
            "causal_test": ca_test_loss,
        },
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Plot results
plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.plot(bl_metrics, label="Baseline")
plt.plot(ca_metrics, label="Causal")
plt.title("Invariant Feature Utilization Score")
plt.xlabel("Epoch")
plt.legend()

plt.subplot(1, 2, 2)
plt.plot(bl_test_loss, label="Baseline")
plt.plot(ca_test_loss, label="Causal")
plt.title("Test Loss")
plt.xlabel("Epoch")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "results.png"))
plt.close()

print(f"\nFinal Results:")
print(f"Baseline IFUS: {bl_metrics[-1]:.4f}")
print(f"Causal IFUS: {ca_metrics[-1]:.4f}")
