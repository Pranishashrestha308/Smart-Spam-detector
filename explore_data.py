import pandas as pd

data = pd.read_csv(
    "dataset/SMSSpamCollection",
    sep="\t",
    header=None,
    names=["label", "message"]
)

# Total number of messages
print("Total messages:", len(data))

# Count spam and normal messages
print("\nMessage categories:")
print(data["label"].value_counts())

# Check missing values
print("\nMissing values:")
print(data.isnull().sum())


import matplotlib.pyplot as plt

# Count messages in each category
data["label"].value_counts().plot(
    kind="bar",
    color=["skyblue", "orange"]
)

plt.title("Spam vs Normal Messages")
plt.xlabel("Message Category")
plt.ylabel("Number of Messages")
plt.show()