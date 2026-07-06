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

# Synthetic data generation
n_samples = 1000
X = np.random.randn(n_samples, 2).astype(np.float32)
y = ((X[:, 0] > 0) & (X[:, 1] > 0)).astype(np.int64)
X_train, y_train = torch.tensor(X[:800]).to(device), torch.tensor(y[:800]).to(device)
X_test, y_test = torch.tensor(X[800:]).to(device), torch.tensor(y[800:]).to(device)


# Model with sparsity regularization
class SparseModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(2, 32)
        self.fc2 = nn.Linear(32, 2)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.relu(self.fc1(x))
        return self.fc2(x)

    def sparsity_loss(self):
        return sum(torch.norm(p, 1) for p in self.parameters())


# Training function
def train_model(sparse=False):
    model = SparseModel().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(100):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        if sparse:
            loss += 0.01 * model.sparsity_loss()
        loss.backward()
        optimizer.step()

        with torch.no_grad():
            test_outputs = model(X_test)
            test_acc = (test_outputs.argmax(1) == y_test).float().mean()

        if epoch % 10 == 0:
            print(f"Epoch {epoch}: loss={loss.item():.4f}, test_acc={test_acc:.4f}")

    return model


# Adversarial attack
def fgsm_attack(model, X, y, epsilon=0.1):
    X.requires_grad = True
    outputs = model(X)
    loss = nn.CrossEntropyLoss()(outputs, y)
    loss.backward()
    perturbation = epsilon * X.grad.sign()
    return torch.clamp(X + perturbation, -3, 3)


# Feature importance
def compute_feature_importance(model, X):
    X.requires_grad = True
    outputs = model(X)
    grads = grad(outputs.sum(), X)[0]
    return torch.abs(grads).mean(0)


# Train and evaluate models
dense_model = train_model(sparse=False)
sparse_model = train_model(sparse=True)

# Adversarial evaluation
X_test_adv = fgsm_attack(dense_model, X_test.clone(), y_test)
dense_adv_acc = (dense_model(X_test_adv).argmax(1) == y_test).float().mean()
sparse_adv_acc = (sparse_model(X_test_adv).argmax(1) == y_test).float().mean()

# Feature importance consistency
dense_imp = compute_feature_importance(dense_model, X_test)
sparse_imp = compute_feature_importance(sparse_model, X_test)

# Save results
experiment_data = {
    "synthetic_data": {
        "metrics": {
            "dense_clean_acc": (dense_model(X_test).argmax(1) == y_test)
            .float()
            .mean()
            .item(),
            "sparse_clean_acc": (sparse_model(X_test).argmax(1) == y_test)
            .float()
            .mean()
            .item(),
            "dense_adv_acc": dense_adv_acc.item(),
            "sparse_adv_acc": sparse_adv_acc.item(),
        },
        "feature_importance": {
            "dense": dense_imp.cpu().numpy(),
            "sparse": sparse_imp.cpu().numpy(),
        },
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Visualization
plt.figure(figsize=(12, 4))
plt.subplot(1, 3, 1)
plt.bar(
    ["Dense", "Sparse"],
    [
        experiment_data["synthetic_data"]["metrics"]["dense_clean_acc"],
        experiment_data["synthetic_data"]["metrics"]["sparse_clean_acc"],
    ],
)
plt.title("Clean Accuracy")

plt.subplot(1, 3, 2)
plt.bar(
    ["Dense", "Sparse"],
    [
        experiment_data["synthetic_data"]["metrics"]["dense_adv_acc"],
        experiment_data["synthetic_data"]["metrics"]["sparse_adv_acc"],
    ],
)
plt.title("Adversarial Accuracy")

plt.subplot(1, 3, 3)
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
plt.legend()
plt.title("Feature Importance")
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "results.png"))
plt.close()

print(
    f"Adversarial Robustness Accuracy - Dense: {dense_adv_acc:.4f}, Sparse: {sparse_adv_acc:.4f}"
)
