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

# Create synthetic dataset
np.random.seed(0)
X = np.random.randn(1000, 2) * 1.5
y = (X[:, 0] * X[:, 1] > 0).astype(int)
X = X.astype(np.float32)
X_train, y_train = torch.tensor(X[:800]).to(device), torch.tensor(y[:800]).to(device)
X_test, y_test = torch.tensor(X[800:]).to(device), torch.tensor(y[800:]).to(device)


# Define models
class Model(nn.Module):
    def __init__(self, sparse=False):
        super().__init__()
        self.fc1 = nn.Linear(2, 32)
        self.fc2 = nn.Linear(32, 2)
        self.sparse = sparse

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        return self.fc2(x)


# Training function
def train_model(sparse=False, l1_lambda=0.01):
    model = Model(sparse).to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(100):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        if sparse:
            l1_norm = sum(p.abs().sum() for p in model.parameters())
            loss = loss + l1_lambda * l1_norm
        loss.backward()
        optimizer.step()

    return model


# FGSM attack
def fgsm_attack(model, X, y, epsilon=0.1):
    X.requires_grad = True
    outputs = model(X)
    loss = nn.CrossEntropyLoss()(outputs, y)
    model.zero_grad()
    loss.backward()
    perturbed_X = X + epsilon * X.grad.sign()
    return perturbed_X.detach()


# Train and evaluate models
dense_model = train_model(sparse=False)
sparse_model = train_model(sparse=True)

# Evaluate clean accuracy
with torch.no_grad():
    dense_acc = (dense_model(X_test).argmax(1) == y_test).float().mean()
    sparse_acc = (sparse_model(X_test).argmax(1) == y_test).float().mean()

# Evaluate adversarial robustness
X_adv = fgsm_attack(dense_model, X_test, y_test)
with torch.no_grad():
    dense_robust_acc = (dense_model(X_adv).argmax(1) == y_test).float().mean()
    sparse_robust_acc = (sparse_model(X_adv).argmax(1) == y_test).float().mean()

# Save results
experiment_data = {
    "synthetic_2d": {
        "metrics": {
            "clean": {"dense": dense_acc.item(), "sparse": sparse_acc.item()},
            "adversarial": {
                "dense": dense_robust_acc.item(),
                "sparse": sparse_robust_acc.item(),
            },
        },
        "sparsity": {
            "dense": sum(
                (p.abs() > 1e-3).sum().item() for p in dense_model.parameters()
            ),
            "sparse": sum(
                (p.abs() > 1e-3).sum().item() for p in sparse_model.parameters()
            ),
        },
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Plot decision boundaries
xx, yy = np.meshgrid(np.linspace(-5, 5, 100), np.linspace(-5, 5, 100))
grid = torch.tensor(np.c_[xx.ravel(), yy.ravel()], dtype=torch.float32).to(device)

with torch.no_grad():
    Z_dense = dense_model(grid).argmax(1).cpu().numpy()
    Z_sparse = sparse_model(grid).argmax(1).cpu().numpy()

plt.figure(figsize=(12, 5))
plt.subplot(1, 2, 1)
plt.contourf(xx, yy, Z_dense.reshape(xx.shape), alpha=0.3)
plt.scatter(X[:, 0], X[:, 1], c=y, edgecolors="k")
plt.title("Dense Model Decision Boundary")
plt.subplot(1, 2, 2)
plt.contourf(xx, yy, Z_sparse.reshape(xx.shape), alpha=0.3)
plt.scatter(X[:, 0], X[:, 1], c=y, edgecolors="k")
plt.title("Sparse Model Decision Boundary")
plt.savefig(os.path.join(working_dir, "decision_boundaries.png"))
plt.close()

print(f"Clean Accuracy - Dense: {dense_acc:.4f}, Sparse: {sparse_acc:.4f}")
print(
    f"Robust Accuracy - Dense: {dense_robust_acc:.4f}, Sparse: {sparse_robust_acc:.4f}"
)
print(
    f"Non-zero Parameters - Dense: {experiment_data['synthetic_2d']['sparsity']['dense']}, Sparse: {experiment_data['synthetic_2d']['sparsity']['sparse']}"
)
