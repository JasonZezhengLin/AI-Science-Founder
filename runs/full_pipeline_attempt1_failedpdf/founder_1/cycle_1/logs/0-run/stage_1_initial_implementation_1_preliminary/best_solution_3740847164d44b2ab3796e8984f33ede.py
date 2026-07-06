import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt

# Setup
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Synthetic data generation
np.random.seed(0)
n_samples = 1000
X = np.random.randn(n_samples, 2) * 1.5
y = (X[:, 0] + X[:, 1] > 0).astype(int)
X_train, y_train = torch.FloatTensor(X[:800]).to(device), torch.LongTensor(y[:800]).to(
    device
)
X_val, y_val = torch.FloatTensor(X[800:]).to(device), torch.LongTensor(y[800:]).to(
    device
)

# Simple logistic regression model
model = nn.Sequential(nn.Linear(2, 1), nn.Sigmoid()).to(device)
optimizer = optim.SGD(model.parameters(), lr=0.1)
criterion = nn.BCELoss()


# Adversarial attack function (FGSM)
def fgsm_attack(model, X, y, epsilon=0.1):
    X.requires_grad = True
    output = model(X)
    loss = criterion(output.squeeze(), y.float())
    loss.backward()
    perturbed_X = X + epsilon * X.grad.sign()
    return perturbed_X.detach()


# Training loop
experiment_data = {
    "synthetic_data": {
        "metrics": {"train": [], "val": [], "adv_val": []},
        "losses": {"train": [], "val": []},
    }
}

n_epochs = 50
lambda_l1 = 0.01  # L1 regularization strength
lambda_adv = 0.5  # Adversarial loss weight

for epoch in range(n_epochs):
    model.train()
    optimizer.zero_grad()

    # Clean forward pass
    outputs = model(X_train).squeeze()
    loss_clean = criterion(outputs, y_train.float())

    # Adversarial training
    X_adv = fgsm_attack(model, X_train, y_train)
    outputs_adv = model(X_adv).squeeze()
    loss_adv = criterion(outputs_adv, y_train.float())

    # L1 regularization for interpretability
    l1_norm = sum(p.abs().sum() for p in model.parameters())

    # Combined loss
    loss = loss_clean + lambda_adv * loss_adv + lambda_l1 * l1_norm
    loss.backward()
    optimizer.step()

    # Evaluation
    model.eval()
    with torch.no_grad():
        # Clean validation
        val_outputs = model(X_val).squeeze()
        val_loss = criterion(val_outputs, y_val.float()).item()
        val_acc = ((val_outputs > 0.5).long() == y_val).float().mean().item()

        # Adversarial validation
        X_val_adv = fgsm_attack(model, X_val, y_val)
        adv_outputs = model(X_val_adv).squeeze()
        adv_acc = ((adv_outputs > 0.5).long() == y_val).float().mean().item()

    # Save metrics
    experiment_data["synthetic_data"]["metrics"]["train"].append(
        ((outputs > 0.5).long() == y_train).float().mean().item()
    )
    experiment_data["synthetic_data"]["metrics"]["val"].append(val_acc)
    experiment_data["synthetic_data"]["metrics"]["adv_val"].append(adv_acc)
    experiment_data["synthetic_data"]["losses"]["train"].append(loss.item())
    experiment_data["synthetic_data"]["losses"]["val"].append(val_loss)

    print(f"Epoch {epoch}: val_acc={val_acc:.4f}, adv_val_acc={adv_acc:.4f}")

# Save results
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Visualization
plt.figure(figsize=(12, 4))
plt.subplot(1, 3, 1)
plt.plot(experiment_data["synthetic_data"]["metrics"]["val"], label="Clean Val Acc")
plt.plot(experiment_data["synthetic_data"]["metrics"]["adv_val"], label="Adv Val Acc")
plt.legend()
plt.title("Accuracy Over Epochs")

# Decision boundary visualization
xx, yy = np.meshgrid(np.linspace(-4, 4, 100), np.linspace(-4, 4, 100))
grid = torch.FloatTensor(np.c_[xx.ravel(), yy.ravel()]).to(device)
with torch.no_grad():
    probs = model(grid).cpu().numpy().reshape(xx.shape)
plt.subplot(1, 3, 2)
plt.contourf(xx, yy, probs > 0.5, alpha=0.3)
plt.scatter(X[:, 0], X[:, 1], c=y, s=5)
plt.title("Decision Boundary")

# Adversarial examples visualization
sample_idx = np.random.choice(len(X_val), 20)
X_sample = X_val[sample_idx].cpu().numpy()
X_adv_sample = fgsm_attack(model, X_val[sample_idx], y_val[sample_idx]).cpu().numpy()
plt.subplot(1, 3, 3)
plt.scatter(X_sample[:, 0], X_sample[:, 1], c="b", label="Original")
plt.scatter(X_adv_sample[:, 0], X_adv_sample[:, 1], c="r", label="Adversarial")
for i in range(len(X_sample)):
    plt.plot(
        [X_sample[i, 0], X_adv_sample[i, 0]],
        [X_sample[i, 1], X_adv_sample[i, 1]],
        "k--",
        alpha=0.3,
    )
plt.legend()
plt.title("Adversarial Examples")

plt.tight_layout()
plt.savefig(os.path.join(working_dir, "results.png"))
plt.close()

# Print final metrics
result = {
    "final_clean_accuracy": experiment_data["synthetic_data"]["metrics"]["val"][-1],
    "final_adversarial_accuracy": experiment_data["synthetic_data"]["metrics"][
        "adv_val"
    ][-1],
    "status": "completed",
}
print(result)
