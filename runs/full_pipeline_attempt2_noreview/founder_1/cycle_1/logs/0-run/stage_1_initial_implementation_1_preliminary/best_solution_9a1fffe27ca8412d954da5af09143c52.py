import os
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
import numpy as np
import matplotlib.pyplot as plt
from torchattacks import PGD
import shap

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

working_dir = os.path.join(os.getcwd(), "working")
os.makedirs(working_dir, exist_ok=True)

# Data preparation
transform = transforms.Compose(
    [transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))]
)
trainset = torchvision.datasets.CIFAR10(
    root="./data", train=True, download=True, transform=transform
)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=128, shuffle=True)
testset = torchvision.datasets.CIFAR10(
    root="./data", train=False, download=True, transform=transform
)
testloader = torch.utils.data.DataLoader(testset, batch_size=128, shuffle=False)


# Model definition
class SimpleCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.fc1 = nn.Linear(64 * 8 * 8, 256)
        self.fc2 = nn.Linear(256, 10)
        self.pool = nn.MaxPool2d(2, 2)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.pool(self.relu(self.conv1(x)))
        x = self.pool(self.relu(self.conv2(x)))
        x = x.view(-1, 64 * 8 * 8)
        x = self.relu(self.fc1(x))
        x = self.fc2(x)
        return x


model = SimpleCNN().to(device)
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()
attack = PGD(model, eps=8 / 255, alpha=2 / 255, steps=10)


# Training with interpretability regularization
def calculate_shap_consistency(model, data, n_samples=50):
    background = data[:100].to(device)
    test_images = data[100:110].to(device)
    explainer = shap.DeepExplainer(model, background)
    shap_values = explainer.shap_values(test_images)
    return np.mean([np.abs(sv).sum() for sv in shap_values])


experiment_data = {
    "cifar10": {
        "metrics": {"train": [], "val": [], "arits": []},
        "losses": {"train": [], "val": []},
    }
}

for epoch in range(5):
    model.train()
    train_loss, correct, total = 0, 0, 0
    for batch_idx, (inputs, targets) in enumerate(trainloader):
        inputs, targets = inputs.to(device), targets.to(device)

        # Adversarial training
        adv_inputs = attack(inputs, targets)
        optimizer.zero_grad()
        outputs = model(adv_inputs)
        loss = criterion(outputs, targets)

        # Interpretability regularization
        if batch_idx % 10 == 0:
            shap_consistency = calculate_shap_consistency(model, inputs)
            loss += 0.1 * (1 - torch.tensor(shap_consistency, device=device))

        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

    train_acc = correct / total
    train_loss = train_loss / len(trainloader)
    experiment_data["cifar10"]["metrics"]["train"].append(train_acc)
    experiment_data["cifar10"]["losses"]["train"].append(train_loss)

    # Evaluation
    model.eval()
    val_loss, val_correct, val_total = 0, 0, 0
    adv_correct = 0
    with torch.no_grad():
        for inputs, targets in testloader:
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = model(inputs)
            val_loss += criterion(outputs, targets).item()
            _, predicted = outputs.max(1)
            val_total += targets.size(0)
            val_correct += predicted.eq(targets).sum().item()

            # Adversarial robustness
            adv_inputs = attack(inputs, targets)
            adv_outputs = model(adv_inputs)
            adv_correct += (adv_outputs.argmax(1) == targets).sum().item()

    val_acc = val_correct / val_total
    adv_acc = adv_correct / val_total
    val_loss = val_loss / len(testloader)
    experiment_data["cifar10"]["metrics"]["val"].append(val_acc)
    experiment_data["cifar10"]["losses"]["val"].append(val_loss)

    # ARITS calculation
    shap_consistency = calculate_shap_consistency(model, next(iter(testloader))[0])
    arits = 2 * (adv_acc * shap_consistency) / (adv_acc + shap_consistency + 1e-8)
    experiment_data["cifar10"]["metrics"]["arits"].append(arits)

    print(f"Epoch {epoch}: Train Loss={train_loss:.4f}, Val Loss={val_loss:.4f}")
    print(
        f"Clean Acc={val_acc:.4f}, Adv Acc={adv_acc:.4f}, SHAP={shap_consistency:.4f}, ARITS={arits:.4f}"
    )

# Save results
np.save(os.path.join(working_dir, "experiment_data.npy"), experiment_data)

# Plot training curves
plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.plot(experiment_data["cifar10"]["losses"]["train"], label="Train Loss")
plt.plot(experiment_data["cifar10"]["losses"]["val"], label="Val Loss")
plt.legend()
plt.title("Loss Curves")

plt.subplot(1, 2, 2)
plt.plot(experiment_data["cifar10"]["metrics"]["train"], label="Train Acc")
plt.plot(experiment_data["cifar10"]["metrics"]["val"], label="Val Acc")
plt.plot(experiment_data["cifar10"]["metrics"]["arits"], label="ARITS")
plt.legend()
plt.title("Metrics")
plt.tight_layout()
plt.savefig(os.path.join(working_dir, "training_curves.png"))
plt.close()
