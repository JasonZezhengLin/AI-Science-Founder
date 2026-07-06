import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Synthetic dataset
n_samples = 1000
X = torch.randn(n_samples, 2).to(device)
y = ((X[:, 0] > 0) & (X[:, 1] > 0)).long().to(device)
X_train, X_test = X[:800], X[800:]
y_train, y_test = y[:800], y[800:]


# Model definition
class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(2, 16)
        self.fc2 = nn.Linear(16, 2)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        return self.fc2(x)


# Training function with sparsity regularization
def train_model(sparsity_weight=0.0):
    model = Net().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(100):
        model.train()
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)

        # Add L1 regularization for sparsity
        l1_reg = torch.tensor(0.0).to(device)
        for param in model.parameters():
            l1_reg += torch.norm(param, 1)
        loss += sparsity_weight * l1_reg

        loss.backward()
        optimizer.step()

        if epoch % 20 == 0:
            model.eval()
            with torch.no_grad():
                preds = model(X_test).argmax(1)
                acc = (preds == y_test).float().mean().item()
            print(f"Epoch {epoch}: Test Acc = {acc:.4f}")

    return model


# FGSM attack function
def fgsm_attack(model, X, y, epsilon=0.1):
    X.requires_grad = True
    outputs = model(X)
    loss = nn.CrossEntropyLoss()(outputs, y)
    loss.backward()

    attack = X + epsilon * X.grad.sign()
    return attack.detach()


# Evaluate models
def evaluate(model, X, y):
    model.eval()
    with torch.no_grad():
        preds = model(X).argmax(1)
        return (preds == y).float().mean().item()


# Train dense and sparse models
dense_model = train_model(sparsity_weight=0.0)
sparse_model = train_model(sparsity_weight=0.01)

# Generate adversarial examples
X_adv = fgsm_attack(dense_model, X_test.clone(), y_test)

# Evaluate robustness
dense_clean_acc = evaluate(dense_model, X_test, y_test)
dense_adv_acc = evaluate(dense_model, X_adv, y_test)
sparse_clean_acc = evaluate(sparse_model, X_test, y_test)
sparse_adv_acc = evaluate(sparse_model, X_adv, y_test)

# Save results
results = {
    "dense": {
        "clean_acc": dense_clean_acc,
        "adv_acc": dense_adv_acc,
        "robustness_drop": dense_clean_acc - dense_adv_acc,
    },
    "sparse": {
        "clean_acc": sparse_clean_acc,
        "adv_acc": sparse_adv_acc,
        "robustness_drop": sparse_clean_acc - sparse_adv_acc,
    },
}

print("\nResults:")
print(
    f"Dense Model - Clean Acc: {dense_clean_acc:.4f}, Adv Acc: {dense_adv_acc:.4f}, Drop: {dense_clean_acc - dense_adv_acc:.4f}"
)
print(
    f"Sparse Model - Clean Acc: {sparse_clean_acc:.4f}, Adv Acc: {sparse_adv_acc:.4f}, Drop: {sparse_clean_acc - sparse_adv_acc:.4f}"
)

# Visualization
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.scatter(X_test[:, 0].cpu(), X_test[:, 1].cpu(), c=y_test.cpu())
plt.title("Original Data")
plt.subplot(1, 2, 2)
plt.scatter(X_adv[:, 0].cpu(), X_adv[:, 1].cpu(), c=y_test.cpu())
plt.title("Adversarial Examples")
plt.savefig(os.path.join(working_dir, "data_visualization.png"))
plt.close()

# Save experiment data
experiment_data = {
    "synthetic_binary": {
        "metrics": results,
        "models": {"dense": str(dense_model), "sparse": str(sparse_model)},
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)
