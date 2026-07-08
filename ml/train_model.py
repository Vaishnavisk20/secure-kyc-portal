import os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score


def generate_synthetic_data(n=2000, random_state=42):
    rng = np.random.RandomState(random_state)
    # Features: face_pct (0-100), name_pct (0-100), verhoeff_flag (0/1), blur_score (0-100)
    face = rng.uniform(0, 100, size=n)
    name = rng.uniform(0, 100, size=n)
    verhoeff = rng.choice([0, 1], size=n, p=[0.2, 0.8])
    blur = rng.uniform(0, 200, size=n)

    X = np.vstack([face, name, verhoeff, blur]).T

    # Simple label rule to simulate fraud: low face & name, invalid verhoeff, or very blurry
    y = ((face < 40) & (name < 50)).astype(int)
    y = np.where(verhoeff == 0, 1, y)
    y = np.where(blur < 40, 1, y)

    return X, y


def train_and_save(path="ml/risk_model.pkl"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    X, y = generate_synthetic_data()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=1)

    clf = RandomForestClassifier(n_estimators=100, random_state=1)
    clf.fit(X_train, y_train)

    probs = clf.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, probs)

    joblib.dump(clf, path)
    print(f"Saved model to {path} (AUC={auc:.3f})")


if __name__ == "__main__":
    train_and_save()
