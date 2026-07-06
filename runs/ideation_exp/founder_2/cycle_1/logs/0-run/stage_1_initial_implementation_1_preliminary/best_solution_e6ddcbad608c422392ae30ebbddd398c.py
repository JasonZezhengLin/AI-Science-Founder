import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Synthetic data
n_train, n_val = 512, 128
x0 = np.random.randn(n_train // 2, 2) * 0.8 + np.array([-1.5, -1.5])
x1 = np.random.randn(n_train // 2, 2) * 0.8 + np.array([1.5, 1.5])
X_train = np.concatenate([x0, x1], axis=0).astype(np.float32)
y_train = np.concatenate(
    [np.zeros(n_train // 2), np.ones(n_train // 2)], axis=0
).astype(np.int64)
x0v = np.random.randn(n_val // 2, 2) * 0.8 + np.array([-1.5, -1.5])
x1v = np.random.randn(n_val // 2, 2) * 0.8 + np.array([1.5, 1.5])
X_val = np.concatenate([x0v, x1v], axis=0).astype(np.float32)
y_val = np.concatenate([np.zeros(n_val // 2), np.ones(n_val // 2)], axis=0).astype(
    np.int64
)

X_train, y_train = torch.tensor(X_train).to(device), torch.tensor(y_train).to(device)
X_val, y_val = torch.tensor(X_val).to(device), torch.tensor(y_val).to(device)

# Model
model = nn.Sequential(nn.Linear(2, 32), nn.ReLU(), nn.Linear(32, 2)).to(device)
optimizer = optim.SGD(model.parameters(), lr=0.1, momentum=0.9)
criterion = nn.CrossEntropyLoss()


# Decision Boundary Complexity Index
def compute_dbci(model, grid_size=100):
    x = np.linspace(-3, 3, grid_size)
    y = np.linspace(-3, 3, grid_size)
    xx, yy = np.meshgrid(x, y)
    grid = np.c_[xx.ravel(), yy.ravel()].astype(np.float32)
    with torch.no_grad():
        logits = model(torch.tensor(grid).to(device))
        probs = (
            torch.softmax(logits, dim=1)[:, 1]
            .cpu()
            .numpy()
            .reshape(grid_size, grid_size)
        )
    probs_smooth = gaussian_filter(probs, sigma=1)
    grad = np.gradient(probs_smooth)
    grad2 = [np.gradient(g) for g in grad]
    curv = np.abs(grad2[0]) + np.abs(grad2[1])
    return curv.mean()


train_losses, val_losses = [], []
train_accs, val_accs = [], []
dbcis = []

for epoch in range(20):
    model.train()
    optimizer.zero_grad()
    logits = model(X_train)
    loss = criterion(logits, y_train)
    loss.backward()
    optimizer.step()

    train_losses.append(loss.item())
    train_acc = (logits.argmax(dim=1) == y_train).float().mean().item()
    train_accs.append(train_acc)

    model.eval()
    with torch.no_grad():
        val_logits = model(X_val)
        val_loss = criterion(val_logits, y_val).item()
        val_accs.append((val_logits.argmax(dim=1) == y_val).float().mean().item())
        val_losses.append(val_loss)
        dbci = compute_dbci(model)
        dbcis.append(dbci)

    print(f"Epoch {epoch}: val_loss={val_loss:.4f}, DBCI={dbci:.4f}")

# Save results
experiment_data = {
    "synthetic_2d": {
        "losses": {"train": train_losses, "val": val_losses},
        "metrics": {"train": train_accs, "val": val_accs},
        "dbcis": dbcis,
    }
}
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Visualization
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.plot(train_losses, label="Train Loss")
plt.plot(val_losses, label="Val Loss")
plt.legend()
plt.title("Loss Over Epochs")

plt.subplot(1, 2, 2)
plt.plot(dbcis)
plt.title("Decision Boundary Complexity Index")
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "training_dynamics.png"))
plt.close()
